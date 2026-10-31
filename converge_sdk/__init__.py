"""Converge SDK: the platform's REST API from Python, standard library only.

    from converge_sdk import ConvergeClient

    client = ConvergeClient()          # CONVERGE_HOSTNAME / CONVERGE_TOKEN, or ~/.converge/config
    client.datasets.get("ri.example.dataset.1")
    client.sql.execute("SELECT count(*) AS n FROM `/Project/orders`")
    o = client.ontology("my-ontology")
    o.objects("Order").take(10)
"""
from .core import ConfigError, ConvergeError, ConvergeRPCError, Transport, UserTokenAuth, resolve
from .datasets import DatasetsClient, SqlClient, SqlError
from .ontologies import (ActionConfig, ActionMode, BatchActionConfig, OntologyClient, ReturnEditsMode,
                         prop)

__version__ = "0.1.0"


class ConvergeClient:
    """``hostname`` is the API base, e.g. ``https://converge.example.com/api``. ``auth``, instead
    of ``token``: a UserTokenAuth, a token, or a callable returning one per request."""

    def __init__(self, hostname=None, token=None, auth=None, timeout=60, config_file=None):
        if auth is None:
            base, tok = resolve(hostname, token, config_file)
            auth = UserTokenAuth(tok)
        else:
            base, _ = resolve(hostname, "unused", config_file)
            if not isinstance(auth, UserTokenAuth):
                auth = UserTokenAuth(auth)
        self._transport = Transport(base, auth, timeout)
        self.datasets = DatasetsClient(self._transport)
        self.sql = SqlClient(self._transport)

    @property
    def transport(self):
        """The transport, for routes the SDK does not wrap (``request(method, path, body)``)."""
        return self._transport

    def ontology(self, ontology_rid):
        return OntologyClient(self._transport, ontology_rid)

    def __repr__(self):
        return "ConvergeClient(%r)" % self._transport.base


__all__ = ["ActionConfig", "ActionMode", "BatchActionConfig", "ConfigError", "ConvergeClient",
           "ConvergeError", "ConvergeRPCError", "DatasetsClient", "OntologyClient", "ReturnEditsMode",
           "SqlClient", "SqlError", "UserTokenAuth", "prop", "__version__"]
