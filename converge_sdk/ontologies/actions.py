"""Actions (single and batch) and queries."""
import types

from ..core.transport import quote
from .objects import Object


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
        return types.SimpleNamespace(validation=r.get("validation"), edits=r.get("edits"))


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
        return types.SimpleNamespace(results=r.get("results"), edits=r.get("edits"))


class Query(Action):
    """A query (function): runs as the caller, read-only; returns its value."""

    def __call__(self, **kwargs):
        r = self._o.request("POST", "/queries/" + quote(self._api_name) + "/execute",
                            {"parameters": self._parameters(kwargs)}) or {}
        return r.get("value")
