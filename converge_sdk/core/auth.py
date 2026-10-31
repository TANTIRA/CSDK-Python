"""Bearer-token authentication."""
import re

from .errors import ConfigError

# a header value: a token with a space or line break (a trailing newline from a file, say) is
# refused here, without echoing it, instead of failing in http.client with the value in the message
_HEADER_SAFE = re.compile(r"[\x21-\x7e]+")


class UserTokenAuth:
    """A bearer token, or a zero-argument callable returning one per request.

    The token is never part of ``repr()``, ``str()`` or an error message."""

    __slots__ = ("_token",)

    def __init__(self, token):
        if not callable(token) and not (isinstance(token, str) and token):
            raise ConfigError("UserTokenAuth needs a non-empty token or a callable")
        self._token = token

    def _get(self):
        t = self._token() if callable(self._token) else self._token
        if not isinstance(t, str) or not _HEADER_SAFE.fullmatch(t):
            raise ConfigError("the token must be printable ASCII without spaces or line breaks")
        return t

    def __repr__(self):
        return "UserTokenAuth(<redacted>)"

    __str__ = __repr__
