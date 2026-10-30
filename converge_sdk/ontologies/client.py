"""Ontology clients: untyped (no generated code) and the class a generated
package builds from its registrations."""
import types

from ..core.auth import UserTokenAuth
from ..core.config import resolve
from ..core.transport import Transport
from .actions import Action, BatchAction, Query
from .attachments import Attachments
from .objects import ObjectSet, Ontology, untyped_class


class OntologyClient:
    """Any ontology the caller can see, by api names::

        o = client.ontology("my-ontology")
        o.objects("Order").where(prop("total") > 5).take(10)
        o.action("place_order")(order_id="o1")
    """

    def __init__(self, transport, ontology_rid):
        self._o = Ontology(transport, ontology_rid)
        self.attachments = Attachments(self._o)

    def objects(self, api_name, primary_key=None):
        return ObjectSet(self._o, untyped_class(api_name, primary_key))

    def action(self, api_name):
        return Action(self._o, api_name)

    def batch_action(self, api_name):
        return BatchAction(self._o, api_name)

    def query(self, api_name):
        return Query(self._o, api_name)


def client_class(ontology_rid, object_types, action_types, query_types=None, name="Client"):
    """The client class of a generated package.

    ``object_types``: python name -> Object subclass; ``action_types`` and
    ``query_types``: python name -> (api name, {python param: (wire name, required)})."""
    object_types = dict(object_types)
    action_types = dict(action_types)
    query_types = dict(query_types or {})
    by_api = {c.object_type._api_name: c for c in object_types.values()}

    def __init__(self, hostname=None, auth=None, timeout=60):
        if auth is None:
            hostname, token = resolve(hostname)
            auth = UserTokenAuth(token)
        elif hostname is None:
            hostname, _ = resolve(None, token="unused")
        base = hostname if "://" in hostname else "https://" + hostname
        o = Ontology(Transport(base, auth, timeout), ontology_rid, by_api)
        self.ontology = types.SimpleNamespace(
            objects=types.SimpleNamespace(**{k: ObjectSet(o, c) for k, c in object_types.items()}),
            actions=types.SimpleNamespace(**{k: Action(o, w, p) for k, (w, p) in action_types.items()}),
            batch_actions=types.SimpleNamespace(**{k: BatchAction(o, w, p)
                                                   for k, (w, p) in action_types.items()}),
            queries=types.SimpleNamespace(**{k: Query(o, w, p) for k, (w, p) in query_types.items()}),
            attachments=Attachments(o),
        )

    return type(name, (), {"__init__": __init__, "ontology_rid": ontology_rid})
