"""HTTP transport: JSON in and out, bearer auth, and no redirects.

urllib would resend the Authorization header to a redirect target, and the
API never redirects, so every redirect is refused: the token never leaves
for another host.
"""
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request

from .config import Config
from .errors import ConfigError, ConvergeRPCError

_LOCAL = {"localhost", "127.0.0.1", "::1"}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ConvergeRPCError(code, "redirect refused")


_OPENER = urllib.request.build_opener(_NoRedirect)


def _opener(config):
    """The default opener, or one with the Config's proxies and TLS verification."""
    if config.proxies is None and config.verify is True:
        return _OPENER
    handlers = [_NoRedirect]
    if config.proxies is not None:
        handlers.append(urllib.request.ProxyHandler(config.proxies))
    if config.verify is not True:
        if config.verify is False:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        elif os.path.isdir(config.verify):
            ctx = ssl.create_default_context(capath=config.verify)
        else:
            ctx = ssl.create_default_context(cafile=config.verify)
        handlers.append(urllib.request.HTTPSHandler(context=ctx))
    return urllib.request.build_opener(*handlers)


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

    def __init__(self, base, auth, timeout=60, config=None):
        # the one place a base URL is accepted: never a bearer token over plain http
        u = urllib.parse.urlsplit(base)
        if u.username is not None or u.password is not None:
            raise ConfigError("the API base may not contain a user name or password")
        if not u.hostname:
            raise ConfigError("the API base has no host; it looks like https://converge.example.com/api")
        if u.scheme != "https" and not (u.scheme == "http" and u.hostname in _LOCAL):
            raise ConfigError("refusing %s://%s: the API base must be https (plain http only for"
                              " localhost)" % (u.scheme or "?", u.hostname))
        self.base = base.rstrip("/")
        self._auth = auth
        config = config if config is not None else Config()
        if not isinstance(config, Config):
            raise ConfigError("config is a converge_sdk.Config")
        self._timeout = config.timeout if config.timeout is not None else timeout
        self._headers = config.default_headers
        self._opener = _opener(config)

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
            **self._headers, "Authorization": "Bearer " + self._auth._get(), **(headers or {})})
        try:
            with self._opener.open(req, timeout=self._timeout) as res:
                return res.read()
        except urllib.error.HTTPError as e:
            if 300 <= e.code < 400:  # one the redirect handler does not follow (300, 304, ...)
                raise ConvergeRPCError(e.code, "redirect refused") from None
            raise ConvergeRPCError(e.code, parse(e.read())) from None
