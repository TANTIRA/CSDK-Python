"""A local HTTP server that answers from a route table and records every request."""
import http.server
import json
import threading


class Stub:
    """``routes``: (method, path) -> (status, body, content type) or a callable(req) -> that.
    Paths match exactly, query string included. ``seen``: (method, path, headers, body bytes)."""

    def __init__(self, routes=None):
        self.routes = dict(routes or {})
        self.seen = []
        stub = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def _handle(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                req = (self.command, self.path, dict(self.headers), body)
                stub.seen.append(req)
                ans = stub.routes.get((self.command, self.path), (404, {"errorCode": "NOT_FOUND"}, None))
                if callable(ans):
                    ans = ans(req)
                status, payload, ctype = ans
                raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                for k, v in ({"Location": payload.decode()} if status in (301, 302, 307, 308) else {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Type", ctype or "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            do_GET = do_POST = do_PUT = do_DELETE = _handle

            def log_message(self, *a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = "http://127.0.0.1:%d/api" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def json_bodies(self):
        """Each request body as JSON; a non-JSON body (a multipart upload) as its bytes."""
        out = []
        for _, _, _, b in self.seen:
            try:
                out.append(json.loads(b) if b else None)
            except ValueError:
                out.append(b)
        return out

    def calls(self):
        return [(m, p) for m, p, _, _ in self.seen]

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def ok(body, status=200, ctype=None):
    return (status, body, ctype)
