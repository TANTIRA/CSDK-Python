"""Actions (single and batch) and queries."""
from ..core.transport import quote
from .objects import GeoPoint, Object, ObjectSet, bare_key
from .responses import BatchApplyActionResponse, SyncApplyActionResponse, ValidateActionResponse
from .where import Property


class ActionMode:
    VALIDATE_ONLY = "VALIDATE_ONLY"
    VALIDATE_AND_EXECUTE = "VALIDATE_AND_EXECUTE"


class ReturnEditsMode:
    ALL = "ALL"
    NONE = "NONE"


class ActionConfig:
    def __init__(self, mode=None, return_edits=None):
        self.mode = mode
        self.return_edits = return_edits


class BatchActionConfig:
    def __init__(self, return_edits=None):
        self.return_edits = return_edits


def _param(v):
    if isinstance(v, Object):  # an object reference parameter takes its primary key
        return v._raw.get(v.object_type._primary_key)
    return v


class Action:
    """``params``: python name -> (wire name, required). None: any keyword, sent as is."""

    def __init__(self, ontology, api_name, params=None):
        self._o = ontology
        self._api_name = api_name
        self._params = params

    def _parameters(self, kwargs):
        if self._params is None:
            return {k: _param(v) for k, v in kwargs.items()}
        unknown = sorted(set(kwargs) - set(self._params))
        if unknown:
            raise TypeError("%s: unknown parameter(s) %s" % (self._api_name, unknown))
        missing = sorted(k for k, (_, req) in self._params.items() if req and k not in kwargs)
        if missing:
            raise TypeError("%s: missing required parameter(s) %s" % (self._api_name, missing))
        return {self._params[k][0]: _param(v) for k, v in kwargs.items()}

    def __call__(self, action_config=None, **kwargs):
        body = {"parameters": self._parameters(kwargs)}
        if action_config is not None:
            opts = {}
            if action_config.mode:
                opts["mode"] = action_config.mode
            if action_config.return_edits:
                opts["returnEdits"] = action_config.return_edits
            if opts:
                body["options"] = opts
        r = self._o.request("POST", "/actions/" + quote(self._api_name) + "/apply", body) or {}
        # an action that needs approval answers 202 with status / approval_id and no validation
        return SyncApplyActionResponse(validation=r.get("validation"), edits=r.get("edits"),
                                       status=r.get("status"), approval_id=r.get("approval_id"))

    def validate(self, **kwargs):
        """Validate only (nothing is written) -> ValidateActionResponse."""
        r = self(action_config=ActionConfig(mode=ActionMode.VALIDATE_ONLY), **kwargs)
        return ValidateActionResponse(r.validation or {})


class BatchAction(Action):
    """``[{...}, ...]``: 1 to 100 requests. Atomic for plain actions; authored or
    approval actions run one at a time and stop at the first failure."""

    def __call__(self, requests, batch_action_config=None):
        if not isinstance(requests, (list, tuple)) or not 1 <= len(requests) <= 100:
            raise ValueError("%s: a batch takes 1 to 100 requests" % self._api_name)
        body = {"requests": [{"parameters": self._parameters(dict(r))} for r in requests]}
        if batch_action_config is not None and batch_action_config.return_edits:
            body["options"] = {"returnEdits": batch_action_config.return_edits}
        r = self._o.request("POST", "/actions/" + quote(self._api_name) + "/applyBatch", body) or {}
        return BatchApplyActionResponse(results=r.get("results"), edits=r.get("edits"))


class Query(Action):
    """A query (function): runs as the caller, read-only; returns its value.

    ``output``: the query type's output data type, from generated code. An object comes back as
    its class, an objectSet as an ObjectSet, an array or set as a list of those, a geopoint as a
    GeoPoint; anything else (a struct is a dict) as sent."""

    def __init__(self, ontology, api_name, params=None, output=None):
        super().__init__(ontology, api_name, params)
        self._output = output

    def __call__(self, **kwargs):
        r = self._o.request("POST", "/queries/" + quote(self._api_name) + "/execute",
                            {"parameters": self._parameters(kwargs)}) or {}
        return _typed(self._o, self._output, r.get("value"))


def _typed(o, dt, v):
    t = dt.get("type") if isinstance(dt, dict) else None
    if v is None or t is None:
        return v
    if t in ("array", "set"):
        return [_typed(o, dt.get("subType"), x) for x in v] if isinstance(v, list) else v
    if t == "geopoint":
        return GeoPoint.from_wire(v) or v
    cls = o.classes.get(dt.get("objectTypeApiName") or dt.get("objectApiName"))
    if cls is None or t not in ("object", "objectSet"):
        return v
    if t == "object":  # the object, or its primary key: then read it as the caller
        return cls(v, o) if isinstance(v, dict) else ObjectSet(o, cls).get(v)
    return _object_set(o, cls, v)


def _object_set(o, cls, v):
    """An objectSet value (a base set, a static set, or the objects / keys as a list) as an
    ObjectSet; it is read again, as the caller, when it is iterated.
    shortcut: a static set is an `or` of `eq` on the primary key, so a very large one can pass
    the server's where limits; page through the query's own output instead if that happens."""
    if isinstance(v, dict) and v.get("type") == "base":
        return ObjectSet(o, cls)
    items = v.get("objects") if isinstance(v, dict) and v.get("type") == "static" else v
    pk = cls.object_type._primary_key
    if not isinstance(items, list) or pk is None:
        return v
    keys = [x.get(pk) if isinstance(x, dict) else bare_key(x) for x in items]
    # an empty set: no object has a null primary key
    where = Property(pk).in_(keys) if keys else Property(pk).is_null()
    return ObjectSet(o, cls).where(where)
