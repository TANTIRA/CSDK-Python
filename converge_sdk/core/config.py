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
