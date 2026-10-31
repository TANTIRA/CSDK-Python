"""Where the hostname and token come from.

In order: the arguments, then the environment (``CONVERGE_HOSTNAME``,
``CONVERGE_TOKEN``, with ``FOUNDRY_TOKEN`` accepted as a fallback for the
token), then the ``[default]`` section of ``~/.converge/config``::

    [default]
    hostname = https://converge.example.com/api
    token = <your token>

Keep that file readable by you only (``chmod 600``).
"""
import configparser
import os
import re
import warnings
from pathlib import Path

from .errors import ConfigError

CONFIG_FILE = Path("~/.converge/config")


def _file_values(path):
    p = Path(os.path.expanduser(str(path)))
    if not p.is_file():
        return {}
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(p, encoding="utf-8")
    except (configparser.Error, UnicodeDecodeError):
        # configparser's message quotes the offending line, which may be the token
        raise ConfigError("%s is not a valid INI file" % path) from None
    return dict(parser["default"]) if parser.has_section("default") else {}


def resolve(hostname=None, token=None, config_file=None):
    """-> (base URL, token). Raises ConfigError naming what is missing, never a value."""
    env = os.environ
    hostname = hostname or env.get("CONVERGE_HOSTNAME")
    token = token or env.get("CONVERGE_TOKEN") or env.get("FOUNDRY_TOKEN")
    if not hostname or not token:
        values = _file_values(config_file or CONFIG_FILE)
        hostname = hostname or values.get("hostname")
        token = token or values.get("token")
    missing = [n for n, v in (("hostname", hostname), ("token", token)) if not v]
    if missing:
        raise ConfigError("no %s: pass it, set CONVERGE_HOSTNAME / CONVERGE_TOKEN, or add it"
                          " to ~/.converge/config" % " or ".join(missing))
    base = hostname if "://" in hostname else "https://" + hostname
    return base.rstrip("/"), token


# RFC 7230 token / visible text: no CR or LF, so a header value can never start a new header
_HEADER_NAME = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
_HEADER_VALUE = re.compile(r"[\x20-\x7e\t]*")


class Config:
    """HTTP options, as in foundry-platform-python::

        FoundryClient(hostname, auth=token, config=Config(default_headers={"X-Team": "ops"},
                      proxies={"https": "http://proxy:3128"}, verify="/etc/ssl/corp-ca.pem", timeout=30))

    ``default_headers`` go on every request; ``Authorization`` is refused (the token comes from
    ``token`` / ``auth`` only). ``proxies``: scheme -> proxy URL, as urllib's ProxyHandler takes it
    (``{}`` turns the ``HTTPS_PROXY`` environment off). ``verify``: True (the system store), a CA
    bundle file or directory, or False, which checks no certificate at all and warns. ``timeout``
    in seconds overrides the client's ``timeout``."""

    def __init__(self, default_headers=None, proxies=None, verify=True, timeout=None):
        headers = dict(default_headers or {})
        for k, v in headers.items():
            # the value is never echoed: it may be a credential of its own
            if not (isinstance(k, str) and _HEADER_NAME.fullmatch(k)
                    and isinstance(v, str) and _HEADER_VALUE.fullmatch(v)):
                raise ConfigError("default_headers: %r is not a valid header name and value" % (k,))
            if k.lower() == "authorization":
                raise ConfigError("default_headers may not set Authorization: pass the token as"
                                  " token= or auth= instead")
        if proxies is not None and not (isinstance(proxies, dict) and all(
                isinstance(k, str) and isinstance(v, str) for k, v in proxies.items())):
            raise ConfigError("proxies is a dict of scheme -> proxy URL, e.g. {\"https\": \"http://proxy:3128\"}")
        if verify is not True and verify is not False:
            if not isinstance(verify, (str, os.PathLike)) or not os.path.exists(verify):
                raise ConfigError("verify is True, False or the path of a CA bundle that exists")
        if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
                                    or timeout <= 0):
            raise ConfigError("timeout is a positive number of seconds")
        if verify is False:
            warnings.warn("Config(verify=False): TLS certificates are NOT checked, so anyone on the"
                          " network path can impersonate the server and read your token. Use"
                          " verify=\"/path/to/ca-bundle.pem\" instead.", stacklevel=2)
        self.default_headers = headers
        self.proxies = None if proxies is None else dict(proxies)
        self.verify = verify
        self.timeout = timeout

    def __repr__(self):
        # names only: a header value or a proxy URL may carry a credential
        return "Config(default_headers=%r, proxies=%r, verify=%r, timeout=%r)" % (
            sorted(self.default_headers), None if self.proxies is None else sorted(self.proxies),
            self.verify, self.timeout)
