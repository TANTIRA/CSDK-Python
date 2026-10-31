"""Python OSDK 2.x parity: one client with the platform API, Config, the response
type names, GeoPoint and typed query outputs."""
import copy
import http.server
import json
import tempfile
import threading
import unittest
import warnings

from converge_sdk import (BatchApplyActionResponse, Config, ConfigError, ConvergeClient, GeoPoint,
                          SyncApplyActionResponse, ValidateActionResponse)
from converge_sdk.core import UserTokenAuth
from converge_sdk.ontologies import Object, ObjectSet, ObjectType, client_class

from .stub import Stub, ok

B = "/api/v2/ontologies/demo"


class Site(Object):
    object_type = ObjectType("Site", "siteId", {"siteId": "siteId", "loc": "loc"}, geo={"loc"})


SITE = {"type": "object", "objectApiName": "Site", "objectTypeApiName": "Site"}
Client = client_class(
    "demo", {"Site": Site},
    {"move": ("move", {"site_id": ("site_id", True)})},
    {"one": ("one", {}, SITE),
     "by_key": ("by_key", {}, SITE),
     "many": ("many", {}, {"type": "array", "subType": SITE}),
     "base": ("base", {}, {"type": "objectSet", "objectTypeApiName": "Site"}),
     "static": ("static", {}, {"type": "objectSet", "objectTypeApiName": "Site"}),
     "none": ("none", {}, {"type": "objectSet", "objectTypeApiName": "Site"}),
     "where": ("where", {}, {"type": "geopoint"}),
     "shape": ("shape", {}, {"type": "struct", "fields": []}),
     "plain": ("plain", {})})


def value(v):
    return ok({"value": v})


def routes():
    s1 = {"$rid": "site/s1", "siteId": "s1", "loc": "52.5,13.4"}
    return {
        ("GET", B + "/objects/Site/site%2Fs1"): ok(s1),
        ("POST", B + "/objects/Site/search"): ok({"data": [s1], "nextPageToken": None}),
        ("POST", B + "/actions/move/apply"): lambda req: ok(
            {"status": "pending_approval", "approval_id": "ap1", "action": "move"}, 202)
            if b"s9" in req[3] else ok({"validation": {"result": "VALID", "submissionCriteria": []},
                                        "edits": {"type": "edits", "addedObjectCount": 1}}),
        ("POST", B + "/actions/move/applyBatch"): ok({"results": [{}], "edits": None}),
        ("POST", B + "/queries/one/execute"): value(s1),
        ("POST", B + "/queries/by_key/execute"): value("s1"),
        ("POST", B + "/queries/many/execute"): value([s1, s1]),
        ("POST", B + "/queries/base/execute"): value({"type": "base", "objectType": "Site"}),
        ("POST", B + "/queries/static/execute"): value({"type": "static", "objects": ["site/s1", "site/s2"]}),
        ("POST", B + "/queries/none/execute"): value([]),
        ("POST", B + "/queries/where/execute"): value({"type": "Point", "coordinates": [13.4, 52.5]}),
        ("POST", B + "/queries/shape/execute"): value({"a": 1}),
        ("POST", B + "/queries/plain/execute"): value(s1),
        ("GET", "/api/v2/datasets/ri.d"): ok({"rid": "ri.d"}),
    }


class OneClientTest(unittest.TestCase):
    def setUp(self):
        self.stub = Stub(routes())
        self.c = Client(self.stub.base, auth=UserTokenAuth("t"),
                        config=Config(default_headers={"X-Team": "ops"}, timeout=5))

    def tearDown(self):
        self.stub.close()

    def test_platform_api_next_to_the_ontology_with_the_config_headers(self):
        self.assertEqual(self.c.datasets.get("ri.d"), {"rid": "ri.d"})
        self.assertTrue(hasattr(self.c, "sql"))
        self.c.ontology.objects.Site.get("s1")
        for _, _, headers, _ in self.stub.seen:
            self.assertEqual((headers["X-Team"], headers["Authorization"]), ("ops", "Bearer t"))
        self.assertEqual(self.c.ontology.objects.Site._o.transport._timeout, 5)

    def test_action_responses_read_as_dicts_and_attributes(self):
        r = self.c.ontology.actions.move(site_id="s1")
        self.assertIsInstance(r, SyncApplyActionResponse)
        self.assertEqual((r.validation["result"], r.validation.result, r["validation"]["result"]),
                         ("VALID", "VALID", "VALID"))
        self.assertEqual(r.validation.submission_criteria, [])
        self.assertEqual((r.edits.added_object_count, r.status, r.approval_id), (1, None, None))
        self.assertEqual(json.loads(json.dumps(r))["edits"]["addedObjectCount"], 1)
        with self.assertRaises(AttributeError):
            r.nope
        pending = self.c.ontology.actions.move(site_id="s9")
        self.assertEqual((pending.status, pending.approval_id, pending.validation), ("pending_approval", "ap1", None))
        v = self.c.ontology.actions.move.validate(site_id="s1")
        self.assertIsInstance(v, ValidateActionResponse)
        self.assertEqual(v.result, "VALID")
        self.assertEqual(self.stub.json_bodies()[-1]["options"], {"mode": "VALIDATE_ONLY"})
        b = self.c.ontology.batch_actions.move([{"site_id": "s1"}])
        self.assertIsInstance(b, BatchApplyActionResponse)
        self.assertEqual((b.results, b.edits), ([{}], None))

    def test_typed_query_outputs(self):
        q = self.c.ontology.queries
        self.assertIsInstance(q.one(), Site)
        self.assertEqual(q.by_key().siteId, "s1")  # a primary key is read as the caller
        self.assertEqual([type(s) for s in q.many()], [Site, Site])
        self.assertIsInstance(q.base(), ObjectSet)
        self.assertNotIn("where", self.stub.json_bodies()[-1] or {})
        q.static().take(5)
        self.assertEqual(self.stub.json_bodies()[-1]["where"], {"type": "or", "conditions": [
            {"type": "eq", "property": "siteId", "value": "s1"},
            {"type": "eq", "property": "siteId", "value": "s2"}]})
        q.none().take(5)
        self.assertEqual(self.stub.json_bodies()[-1]["where"]["type"], "isNull")
        self.assertEqual((q.where().latitude, q.where().longitude), (52.5, 13.4))
        self.assertEqual(q.shape(), {"a": 1})
        self.assertIsInstance(q.plain(), dict)  # no declared output: as sent

    def test_geopoint_properties(self):
        s = self.c.ontology.objects.Site.get("s1")
        self.assertIsInstance(s.loc, GeoPoint)
        self.assertEqual((s.loc, s.loc.latitude, s.loc.longitude), ("52.5,13.4", 52.5, 13.4))
        self.assertEqual(json.dumps(s.loc), '"52.5,13.4"')
        self.assertEqual(copy.deepcopy(s.loc).longitude, 13.4)
        for bad in ("nope", "91,0", "1,2,3", {"type": "LineString"}, '{"type":', None, 5):
            self.assertIsNone(GeoPoint.from_wire(bad))
        self.assertEqual(GeoPoint.from_wire('{"type": "Point", "coordinates": [1, 2]}'), "2,1")


class ConfigTest(unittest.TestCase):
    def test_authorization_and_broken_headers_are_refused_without_their_value(self):
        for k in ("Authorization", "authorization", "AUTHORIZATION"):
            with self.assertRaises(ConfigError) as e:
                Config(default_headers={k: "Bearer stolen"})
            self.assertIn("Authorization", str(e.exception))
            self.assertNotIn("stolen", str(e.exception))
        for h in ({"X-A": "v\r\nX-Evil: 1"}, {"X A": "v"}, {"X-A": 1}):
            with self.assertRaises(ConfigError) as e:
                Config(default_headers=h)
            self.assertNotIn("Evil", str(e.exception))
        for bad in ({"proxies": "http://p"}, {"verify": "/nonexistent/ca.pem"}, {"timeout": 0},
                    {"timeout": True}):
            with self.assertRaises(ConfigError):
                Config(**bad)
        with self.assertRaises(ConfigError):
            ConvergeClient("https://h.example/api", token="t", config={"timeout": 1})

    def test_repr_names_no_header_value_or_proxy_url(self):
        r = repr(Config(default_headers={"X-Key": "s3cret"}, proxies={"https": "http://u:pw@p:1"}))
        self.assertNotIn("s3cret", r)
        self.assertNotIn("pw", r)

    def test_verify_false_warns_and_a_ca_bundle_is_accepted(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Config(verify=False)
        self.assertIn("NOT checked", str(w[0].message))
        with tempfile.NamedTemporaryFile(suffix=".pem") as f, tempfile.TemporaryDirectory() as d:
            for path in (d, f.name):
                with warnings.catch_warnings():
                    warnings.simplefilter("error")
                    Config(verify=path)

    def test_proxies_go_through_urllib_proxy_handler(self):
        seen = []

        class Proxy(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # a plain-http proxy gets the absolute URL
                seen.append(self.path)
                body = b'{"rid": "via-proxy"}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            proxy = "http://127.0.0.1:%d" % server.server_address[1]
            c = ConvergeClient("http://localhost:9/api", token="t", config=Config(proxies={"http": proxy}))
            self.assertEqual(c.datasets.get("ri.x"), {"rid": "via-proxy"})
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(seen, ["http://localhost:9/api/v2/datasets/ri.x"])


if __name__ == "__main__":
    unittest.main()
