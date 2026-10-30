"""HTTP transport: JSON in and out, bearer auth, and no redirects.

urllib would resend the Authorization header to a redirect target, and the
API never redirects, so every redirect is refused: the token never leaves
for another host.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

from .errors import ConfigError, ConvergeRPCError

_LOCAL = {"localhost", "127.0.0.1", "::1"}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ConvergeRPCError(code, "redirect refused: %s" % newurl)


_OPENER = urllib.request.build_opener(_NoRedirect)


def parse(raw):
    """JSON, else the text, else None for an empty body."""
    text = raw.decode("utf-8", "replace")
    try:
        return json.loads(text) if text else None
    except ValueError:
        return text


def quote(s):
    """One path segment."""
    return urllib.parse.quote(str(s), safe="")


class Transport:
    """Requests against one API base URL (e.g. ``https://host/api``)."""

    def __init__(self, base, auth, timeout=60):
        # the one place a base URL is accepted: never a bearer token over plain http
        u = urllib.parse.urlsplit(base)
        if u.scheme != "https" and not (u.scheme == "http" and u.hostname in _LOCAL):
            raise ConfigError("refusing %s://%s: the API base must be https (plain http only for"
                              " localhost)" % (u.scheme or "?", u.hostname or "?"))
        self.base = base.rstrip("/")
        self._auth = auth
        self._timeout = timeout

    def __repr__(self):
        return "Transport(%r)" % self.base

    def request(self, method, path, body=None):
        """JSON request to ``base + path`` -> the parsed answer."""
        headers, data = {}, None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        return parse(self.send(method, self.base + path, data, headers))

    def send(self, method, url, data=None, headers=None):
        """The raw response bytes of one request to a full URL."""
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": "Bearer " + self._auth._get(), **(headers or {})})
        try:
            with _OPENER.open(req, timeout=self._timeout) as res:
                return res.read()
        except urllib.error.HTTPError as e:
            raise ConvergeRPCError(e.code, parse(e.read())) from None
