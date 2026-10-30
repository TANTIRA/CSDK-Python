"""Bearer-token authentication."""


class UserTokenAuth:
    """A bearer token, or a zero-argument callable returning one per request.

    The token is never part of ``repr()``, ``str()`` or an error message."""

    __slots__ = ("_token",)

    def __init__(self, token):
        if not callable(token) and not (isinstance(token, str) and token):
            raise ValueError("UserTokenAuth needs a non-empty token or a callable")
        self._token = token

    def _get(self):
        return self._token() if callable(self._token) else self._token

    def __repr__(self):
        return "UserTokenAuth(<redacted>)"

    __str__ = __repr__
