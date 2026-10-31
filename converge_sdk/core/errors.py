"""Errors raised by the SDK. A message never contains a token."""


class ConvergeError(Exception):
    """Base class of every SDK error."""


class ConvergeRPCError(ConvergeError):
    """A non-2xx answer from the API (a refused redirect included): ``.status``, the parsed
    ``.body`` and the API's ``.error_name`` (``.name`` is the same, kept for earlier code)."""

    def __init__(self, status, body):
        super().__init__("request failed with HTTP %s" % status)
        self.status = status
        self.body = body
        name = body.get("errorName") if isinstance(body, dict) else None
        self.error_name = name if isinstance(name, str) else None
        self.name = self.error_name
        self.parameters = body.get("parameters") if isinstance(body, dict) else None


class ConfigError(ConvergeError, ValueError):
    """No hostname or token could be found, or one of them is not usable."""
