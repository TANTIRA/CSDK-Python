"""The ontology runtime against a stub server, typed (as a generated package
builds it) and untyped. Synthetic ontology "demo": Order and Customer."""
import json
import unittest

from converge_sdk import ActionConfig, ActionMode, BatchActionConfig, ConvergeClient, ReturnEditsMode, prop
from converge_sdk.core import ConvergeRPCError, UserTokenAuth
from converge_sdk.ontologies import Object, ObjectType, client_class

from .stub import Stub, ok

B = "/api/v2/ontologies/demo"


class Order(Object):
    object_type = ObjectType("Order", "orderId", {"orderId": "orderId", "total": "total"},
                             {"placedBy": "Customer"})


class Customer(Object):
    object_type = ObjectType("Customer", "customerId", {"customerId": "customerId", "name": "name"})


Client = client_class("demo", {"Order": Order, "Customer": Customer},
                      {"place_order": ("place_order", {"order_id": ("order_id", True),
                                                       "note": ("note", False)})},
                      {"score": ("score", {"order_rid": ("order_rid", True)})})


def routes():
    return {
        ("POST", B + "/objects/Order/search"): lambda req: ok(
            {"data": [{"$rid": "order/o1", "orderId": "o1", "total": 5}],
             "nextPageToken": None if b"pageToken" in req[3] else "p2", "totalCount": "2"}),
        ("GET", B + "/objects/Order/order%2Fo1"): ok({"$rid": "order/o1", "orderId": "o1", "total": 5}),
        ("GET", B + "/objects/Order/o1/links/placedBy?pageSize=100"):
            ok({"data": [{"$rid": "customer/c1", "customerId": "c1", "name": "Ada"}], "nextPageToken": None}),
        ("POST", B + "/objects/Order/aggregate"):
            ok({"accuracy": "ACCURATE", "data": [{"group": {}, "metrics": [{"name": "count", "value": 2}]}]}),
        ("POST", B + "/actions/place_order/apply"): ok({"validation": {"result": "VALID"}, "edits": None}),
        ("POST", B + "/actions/place_order/applyBatch"): ok({"results": [{}, {}], "edits": None}),
        ("POST", B + "/queries/score/execute"): ok({"value": 0.5}),
        ("POST", "/api/v2/ontologies/attachments/upload"): ok({"rid": "ri.att.1"}),
        ("GET", "/api/v2/ontologies/attachments/ri.att.1/content"): ok(b"\x00\x01", 200, "application/octet-stream"),
    }


class TypedClientTest(unittest.TestCase):
    def setUp(self):
        self.stub = Stub(routes())
        self.c = Client(self.stub.base, auth=UserTokenAuth("t"))

    def tearDown(self):
        self.stub.close()

    def test_reads_build_the_wire_requests(self):
        orders = self.c.ontology.objects.Order
        q = orders.where((Order.object_type.total > 1) & Order.object_type.orderId.in_(["o1", "o2"])) \
            .order_by(Order.object_type.total.desc()).select(Order.object_type.total)
        self.assertEqual([o.orderId for o in q.iterate(page_size=1)], ["o1", "o1"])
        self.assertEqual(orders.get("o1").total, 5)
        owner = list(orders.linked("order/o1", "placedBy").iterate(page_size=100))
        self.assertIsInstance(owner[0], Customer)
        self.assertEqual(orders.count().compute(), 2)
        orders.aggregate("count", group_by=[{"field": Order.object_type.total, "fixedWidth": 10}])
        with self.assertRaises(ValueError):
            orders.linked("o1", "nope")
        total = Order.object_type.total
        gt = {"type": "gt", "property": "total", "value": 1}
        self.assertEqual((~(total > 1))._wire, {"type": "not", "conditions": [gt]})
        self.assertEqual((~~(total > 1))._wire, gt)  # cancels: depth is capped at 5
        self.assertEqual((total != 3)._wire, {"type": "not", "conditions": [
            {"type": "eq", "property": "total", "value": 3}]})
        self.assertEqual(total.is_null(False)._wire, {"type": "not", "conditions": [
            {"type": "isNull", "property": "total", "value": True}]})
        # subtract: the orders over 1 that are not o1
        self.assertEqual(((total > 1) & ~Order.object_type.orderId.in_(["o1"]))._wire,
                         {"type": "and", "conditions": [gt, {"type": "not", "conditions": [
                             {"type": "eq", "property": "orderId", "value": "o1"}]}]})
        bodies = self.stub.json_bodies()
        where = {"type": "and", "conditions": [
            {"type": "gt", "property": "total", "value": 1},
            {"type": "or", "conditions": [{"type": "eq", "property": "orderId", "value": "o1"},
                                          {"type": "eq", "property": "orderId", "value": "o2"}]}]}
        self.assertEqual(bodies[0], {"pageSize": 1, "where": where,
                                     "orderBy": {"property": "total", "direction": "desc"},
                                     "select": ["total"]})
        self.assertEqual(bodies[1]["pageToken"], "p2")
        self.assertEqual(bodies[-1], {"aggregation": {"type": "count", "group_by": [
            {"field": "total", "fixedWidth": 10}]}})

    def test_where_none_starts_with_and_set_edges(self):
        total, oid = Order.object_type.total, Order.object_type.orderId
        self.assertEqual((total == None)._wire, {"type": "isNull", "property": "total", "value": True})  # noqa: E711
        self.assertEqual((total != None)._wire, {"type": "not", "conditions": [  # noqa: E711
            {"type": "isNull", "property": "total", "value": True}]})
        self.assertEqual(oid.starts_with("o.1(")._wire, {"type": "regex", "property": "orderId",
                                                          "value": "o\\.1\\([\\s\\S]*"})
        orders = self.c.ontology.objects.Order
        self.assertIs(orders.where(), orders)
        self.assertEqual((oid.contains_any_term("a b") & ~oid.contains_all_terms_in_order("big re"))._wire,
                         {"type": "and", "conditions": [
                             {"type": "containsAnyTerm", "property": "orderId", "value": "a b"},
                             {"type": "not", "conditions": [
                                 {"type": "containsAllTermsInOrder", "property": "orderId", "value": "big re"}]}]})
        self.assertEqual(oid.contains_all_terms("x")._wire["type"], "containsAllTerms")
        self.assertEqual(oid.contains_all_terms_in_order_prefix_last_term("x")._wire["type"],
                         "containsAllTermsInOrderPrefixLastTerm")
        self.assertEqual([o.orderId for o in orders.list(page_size=1)], ["o1", "o1"])  # both pages
        for bad in ("total", {"property": "total", "direction": "up"}, {"property": "total"}):
            with self.assertRaises(TypeError):
                orders.order_by(bad)
        self.assertIsInstance(orders.count().compute(), int)
        self.c.ontology.actions.place_order(order_id="o9", action_config=ActionConfig())
        self.assertNotIn("options", self.stub.json_bodies()[-1])

    def test_actions_queries_and_attachments(self):
        o = self.c.ontology
        r = o.actions.place_order(order_id="o9",
                                  action_config=ActionConfig(ActionMode.VALIDATE_ONLY, ReturnEditsMode.ALL))
        self.assertEqual(r.validation, {"result": "VALID"})
        o.batch_actions.place_order([{"order_id": "a"}, {"order_id": "b", "note": "x"}],
                                    batch_action_config=BatchActionConfig(ReturnEditsMode.ALL))
        self.assertEqual(o.queries.score(order_rid="order/o1"), 0.5)
        for bad in (lambda: o.actions.place_order(), lambda: o.actions.place_order(order_id=1, nope=2),
                    lambda: o.batch_actions.place_order([])):
            with self.assertRaises((TypeError, ValueError)):
                bad()
        self.assertEqual(o.attachments.upload(b"abc", 'a".txt', "text/plain")["rid"], "ri.att.1")
        self.assertEqual(o.attachments.read("ri.att.1"), b"\x00\x01")
        with self.assertRaises(ValueError):
            o.attachments.upload(b"x", "a.txt", "text/plain\r\nX-Evil: 1")
        bodies = self.stub.json_bodies()
        self.assertEqual(bodies[0], {"parameters": {"order_id": "o9"},
                                     "options": {"mode": "VALIDATE_ONLY", "returnEdits": "ALL"}})
        self.assertEqual(bodies[1], {"requests": [{"parameters": {"order_id": "a"}},
                                                  {"parameters": {"order_id": "b", "note": "x"}}],
                                     "options": {"returnEdits": "ALL"}})
        self.assertEqual(bodies[2], {"parameters": {"order_rid": "order/o1"}})
        upload = self.stub.seen[3]
        self.assertIn(b'filename="a_.txt"', upload[3])
        self.assertTrue(upload[2]["Content-Type"].startswith("multipart/form-data; boundary="))


class UntypedClientTest(unittest.TestCase):
    def test_same_requests_without_generated_code(self):
        stub = Stub(routes())
        try:
            o = ConvergeClient(stub.base, token="t").ontology("demo")
            rows = o.objects("Order").where(prop("total") > 1).take(1)
            self.assertEqual(rows[0]["total"], 5)
            self.assertEqual(rows[0].raw["orderId"], "o1")
            o.action("place_order")(order_id="o9")
            self.assertEqual(o.query("score")(order_rid="order/o1"), 0.5)
            with self.assertRaises(ConvergeRPCError):
                o.objects("Nope").take(1)
        finally:
            stub.close()
        self.assertEqual(stub.calls()[:3], [("POST", B + "/objects/Order/search"),
                                            ("POST", B + "/actions/place_order/apply"),
                                            ("POST", B + "/queries/score/execute")])
        self.assertEqual(json.loads(stub.seen[0][3])["where"], {"type": "gt", "property": "total", "value": 1})


if __name__ == "__main__":
    unittest.main()
