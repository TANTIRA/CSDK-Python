"""Datasets and SQL against a stub server, with synthetic rids and rows."""
import unittest

from converge_sdk import ConvergeClient, SqlError

from .stub import Stub, ok

D = "/api/v2/datasets"
RID = "ri.example.dataset.1"


def tx(status):
    return ok({"rid": "ri.example.tx.1", "datasetRid": RID, "branch": "master",
               "transactionType": "APPEND", "status": status})


class DatasetsTest(unittest.TestCase):
    def setUp(self):
        self.stub = Stub({
            ("POST", D): ok({"rid": RID, "name": "orders"}),
            ("GET", D + "/" + RID): ok({"rid": RID, "name": "orders"}),
            ("GET", D + "?pageSize=1"): ok({"data": [{"rid": "a"}], "nextPageToken": "1"}),
            ("GET", D + "?pageSize=1&pageToken=1"): ok({"data": [{"rid": "b"}], "nextPageToken": None}),
            ("POST", D + "/%s/branches" % RID): ok({"name": "dev"}),
            ("GET", D + "/%s/branches" % RID): ok({"data": [{"name": "master"}], "nextPageToken": None}),
            ("PUT", D + "/%s/branches/master/schema" % RID): ok({"columns": []}),
            ("POST", D + "/%s/branches/master/transactions" % RID): tx("OPEN"),
            ("POST", D + "/%s/transactions/ri.example.tx.1/rows" % RID): ok({"staged": 2}),
            ("POST", D + "/%s/transactions/ri.example.tx.1/files" % RID): ok({"path": "a.csv"}),
            ("POST", D + "/%s/transactions/ri.example.tx.1/commit" % RID): tx("COMMITTED"),
            ("POST", D + "/%s/transactions/ri.example.tx.1/abort" % RID): tx("ABORTED"),
            ("GET", D + "/%s/branches/master/readTable?format=json&limit=1" % RID):
                ok({"schema": {"columns": []}, "rows": [{"id": 1}], "nextPageToken": "1"}),
            ("GET", D + "/%s/branches/master/readTable?format=json&limit=1&pageToken=1" % RID):
                ok({"schema": {"columns": []}, "rows": [{"id": 2}], "nextPageToken": None}),
        })
        self.c = ConvergeClient(self.stub.base, token="t")

    def tearDown(self):
        self.stub.close()

    def test_catalog_branches_schema_and_rows(self):
        ds = self.c.datasets
        self.assertEqual(ds.create("orders", parent_folder_rid="ri.example.folder.1")["rid"], RID)
        self.assertEqual(ds.get(RID)["name"], "orders")
        self.assertEqual([d["rid"] for d in ds.iterate(page_size=1)], ["a", "b"])
        ds.create_branch(RID, "dev", parent_branch="master")
        self.assertEqual(ds.list_branches(RID), [{"name": "master"}])
        ds.put_schema(RID, [{"name": "id", "type": "integer"}], primary_key=["id"])
        self.assertEqual([r["id"] for r in ds.iterate_rows(RID, page_size=1)], [1, 2])
        bodies = self.stub.json_bodies()
        self.assertEqual(bodies[0], {"name": "orders", "parentFolderRid": "ri.example.folder.1"})
        self.assertEqual(bodies[4], {"name": "dev", "parentBranch": "master"})
        self.assertEqual(bodies[6], {"columns": [{"name": "id", "type": "integer"}], "primaryKey": ["id"]})

    def test_a_transaction_commits_on_success_and_aborts_on_error(self):
        with self.c.datasets.transaction(RID) as t:
            self.assertEqual(t.write_rows([{"id": 1}, {"id": 2}]), 2)
            t.upload_file("a.csv", b"id\n3\n", "text/csv")
        self.assertEqual(t.info["status"], "COMMITTED")
        with self.assertRaises(RuntimeError):
            with self.c.datasets.transaction(RID) as t2:
                raise RuntimeError("boom")
        self.assertEqual(t2.info["status"], "ABORTED")
        ends = [p.rsplit("/", 1)[1] for _, p in self.stub.calls()]
        self.assertEqual(ends, ["transactions", "rows", "files", "commit", "transactions", "abort"])
        self.assertEqual(self.stub.json_bodies()[0], {"transactionType": "APPEND"})


class SqlTest(unittest.TestCase):
    def test_execute_polls_then_reads_csv(self):
        states = iter([{"type": "running", "queryId": "q1"}, {"type": "succeeded", "queryId": "q1"}])
        stub = Stub({
            ("POST", "/api/v2/sqlQueries/execute"): ok({"type": "running", "queryId": "q1"}),
            ("GET", "/api/v2/sqlQueries/q1/getStatus"): lambda req: ok(next(states)),
            ("GET", "/api/v2/sqlQueries/q1/getResults"): ok(b"n,name\n2,a\n", 200, "text/csv"),
        })
        try:
            rows = ConvergeClient(stub.base, token="t").sql.execute("SELECT 1", poll=0.01)
        finally:
            stub.close()
        self.assertEqual(rows, [{"n": "2", "name": "a"}])
        self.assertEqual(stub.json_bodies()[0], {"query": "SELECT 1", "fallbackBranchIds": [],
                                                 "serializationFormat": "CSV"})

    def test_a_failed_query_raises(self):
        stub = Stub({("POST", "/api/v2/sqlQueries/execute"): ok({"type": "failed", "errorMessage": "bad sql"})})
        try:
            with self.assertRaises(SqlError) as e:
                ConvergeClient(stub.base, token="t").sql.execute("SELEC")
        finally:
            stub.close()
        self.assertIn("bad sql", str(e.exception))


if __name__ == "__main__":
    unittest.main()
