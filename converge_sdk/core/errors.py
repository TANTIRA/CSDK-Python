"""Errors raised by the SDK. A message never contains a token."""


class ConvergeError(Exception):
    """Base class of every SDK error."""


class ConvergeRPCError(ConvergeError):
    """A non-2xx answer from the API: ``.status`` and the parsed ``.body``."""

    def __init__(self, status, body):
        super().__init__("request failed with HTTP %s" % status)
        self.status = status
        self.body = body
        self.name = body.get("errorName") if isinstance(body, dict) else None
        self.parameters = body.get("parameters") if isinstance(body, dict) else None


class ConfigError(ConvergeError):
    """No hostname or token could be found (argument, environment or config file)."""
