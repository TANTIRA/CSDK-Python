"""Datasets: catalog, branches, schema, transactions, files, rows and SQL.

Covers the routes the server has under /v2/datasets and /v2/sqlQueries.
Not available yet (no server route the SDK uses): dataset views, projections,
retention policies, Iceberg tables and the SQL job list.
"""
import csv
import io
import secrets
import time
import urllib.parse

from ..core.errors import ConvergeError
from ..core.transport import parse, quote

_DS = "/v2/datasets"


def _qs(**params):
    q = {k: v for k, v in params.items() if v is not None}
    return ("?" + urllib.parse.urlencode(q)) if q else ""


def _pages(fetch, page_size):
    token = None
    while True:
        r = fetch(page_size, token) or {}
        for x in r.get("data") or []:
            yield x
        token = r.get("nextPageToken")
        if not token:
            return


class Transaction:
    """An open transaction. As a context manager it commits on success and
    aborts when the block raises::

        with client.datasets.transaction(rid, "master", "APPEND") as tx:
            tx.write_rows([{"id": 1}])
    """

    def __init__(self, transport, dataset_rid, info):
        self._t = transport
        self.dataset_rid = dataset_rid
        self.info = info
        self.rid = info["rid"]

    def _path(self, suffix):
        return "%s/%s/transactions/%s%s" % (_DS, quote(self.dataset_rid), quote(self.rid), suffix)

    def write_rows(self, rows):
        """Stage rows (dicts) in this transaction -> how many were staged."""
        rows = list(rows)
        return (self._t.request("POST", self._path("/rows"), {"rows": rows}) or {}).get("staged")

    def upload_file(self, filename, data, media_type="application/octet-stream"):
        """Stage one file (bytes). A .csv file is parsed into rows on commit."""
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("upload_file(filename, data): data must be bytes")
        name = "".join("_" if c in '"\\\r\n' else c for c in str(filename)) or "unnamed"
        if any(c in str(media_type) for c in "\r\n"):
            raise ValueError("upload_file: media_type may not contain a line break")
        bnd = "csdk" + secrets.token_hex(16)
        body = ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
                "Content-Type: %s\r\n\r\n" % (bnd, name, media_type)).encode() + bytes(data) \
            + ("\r\n--%s--\r\n" % bnd).encode()
        return parse(self._t.send("POST", self._t.base + self._path("/files"), body,
                                  {"Content-Type": "multipart/form-data; boundary=" + bnd}))

    def commit(self):
        self.info = self._t.request("POST", self._path("/commit"))
        return self.info

    def abort(self):
        self.info = self._t.request("POST", self._path("/abort"))
        return self.info

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.commit()
        else:
            self.abort()
        return False


class DatasetsClient:
    def __init__(self, transport):
        self._t = transport

    # ---- catalog
    def create(self, name, parent_folder_rid=None, description=None):
        body = {"name": name}
        if parent_folder_rid is not None:
            body["parentFolderRid"] = parent_folder_rid
        if description is not None:
            body["description"] = description
        return self._t.request("POST", _DS, body)

    def get(self, rid):
        return self._t.request("GET", "%s/%s" % (_DS, quote(rid)))

    def iterate(self, page_size=100):
        """Every dataset the caller can read, page by page."""
        return _pages(lambda n, tok: self._t.request("GET", _DS + _qs(pageSize=n, pageToken=tok)),
                      page_size)

    def delete(self, rid):
        return self._t.request("DELETE", "%s/%s" % (_DS, quote(rid)))

    # ---- branches
    def create_branch(self, rid, name, parent_branch=None, from_transaction=None):
        body = {"name": name}
        if parent_branch is not None:
            body["parentBranch"] = parent_branch
        if from_transaction is not None:
            body["fromTransaction"] = from_transaction
        return self._t.request("POST", "%s/%s/branches" % (_DS, quote(rid)), body)

    def list_branches(self, rid):
        return (self._t.request("GET", "%s/%s/branches" % (_DS, quote(rid))) or {}).get("data") or []

    def delete_branch(self, rid, branch):
        return self._t.request("DELETE", "%s/%s/branches/%s" % (_DS, quote(rid), quote(branch)))

    # ---- schema
    def get_schema(self, rid, branch="master"):
        return self._t.request("GET", "%s/%s/branches/%s/schema" % (_DS, quote(rid), quote(branch)))

    def put_schema(self, rid, columns, branch="master", primary_key=None):
        """``columns``: [{"name": ..., "type": ...}, ...]."""
        body = {"columns": list(columns)}
        if primary_key is not None:
            body["primaryKey"] = list(primary_key)
        return self._t.request("PUT", "%s/%s/branches/%s/schema" % (_DS, quote(rid), quote(branch)), body)

    # ---- transactions
    def transaction(self, rid, branch="master", transaction_type="APPEND"):
        """Open a transaction: APPEND, UPDATE, DELETE or SNAPSHOT."""
        info = self._t.request("POST", "%s/%s/branches/%s/transactions" % (_DS, quote(rid), quote(branch)),
                               {"transactionType": transaction_type})
        return Transaction(self._t, rid, info)

    # ---- files and rows
    def list_files(self, rid, branch="master"):
        return (self._t.request("GET", "%s/%s/branches/%s/files" % (_DS, quote(rid), quote(branch)))
                or {}).get("data") or []

    def read_file(self, rid, file_rid):
        """The bytes of one file."""
        return self._t.send("GET", self._t.base + "%s/%s/files/%s/content" % (_DS, quote(rid), quote(file_rid)))

    def read_table(self, rid, branch="master", limit=1000, page_token=None,
                   filter_column=None, filter_op=None, filter_value=None):
        """One page of committed rows: {"schema": ..., "rows": [...], "nextPageToken": ...}."""
        return self._t.request("GET", "%s/%s/branches/%s/readTable" % (_DS, quote(rid), quote(branch))
                               + _qs(format="json", limit=limit, pageToken=page_token,
                                     filterColumn=filter_column, filterOp=filter_op,
                                     filterValue=filter_value))

    def iterate_rows(self, rid, branch="master", page_size=1000, **filters):
        token = None
        while True:
            r = self.read_table(rid, branch, limit=page_size, page_token=token, **filters) or {}
            for row in r.get("rows") or []:
                yield row
            token = r.get("nextPageToken")
            if not token:
                return


class SqlError(ConvergeError):
    """The SQL query failed or was canceled on the server."""


class SqlClient:
    """SQL over datasets (backtick their paths or rids) or the platform tables."""

    def __init__(self, transport):
        self._t = transport

    def execute(self, query, fallback_branch_ids=None, timeout=60.0, poll=0.25):
        """Run a query and return its rows as dicts (values as text, from CSV)."""
        r = self._t.request("POST", "/v2/sqlQueries/execute", {
            "query": query, "fallbackBranchIds": list(fallback_branch_ids or []),
            "serializationFormat": "CSV"}) or {}
        deadline = time.monotonic() + timeout
        while r.get("type") == "running":
            if time.monotonic() > deadline:
                raise SqlError("query %s still running after %ss" % (r.get("queryId"), timeout))
            time.sleep(poll)
            r = self._t.request("GET", "/v2/sqlQueries/%s/getStatus" % quote(r["queryId"])) or {}
        if r.get("type") != "succeeded":
            raise SqlError(r.get("errorMessage") or "query %s" % r.get("type"))
        raw = self._t.send("GET", self._t.base + "/v2/sqlQueries/%s/getResults" % quote(r["queryId"]))
        return list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
