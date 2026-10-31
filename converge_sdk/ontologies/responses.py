"""Action responses under their Python OSDK 2.x names.

Each is a dict (JSON-serialisable, ``r["validation"]["result"]`` as before) whose keys
also read as attributes, snake_case or as sent: ``r.validation.result``,
``r.validation.submission_criteria``.
"""
import re


def _record(v):
    if isinstance(v, dict) and not isinstance(v, Record):
        return Record(v)
    if isinstance(v, list):
        return [_record(x) for x in v]
    return v


class Record(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for k, v in self.items():
            dict.__setitem__(self, k, _record(v))

    def __getattr__(self, name):
        for k in (name, re.sub(r"_([a-z0-9])", lambda m: m.group(1).upper(), name)):
            if k in self:
                return self[k]
        raise AttributeError(name)

    def __repr__(self):
        return "%s(%s)" % (type(self).__name__, dict.__repr__(self))


class SyncApplyActionResponse(Record):
    """``validation`` (result, submissionCriteria, parameters) and ``edits`` (None unless
    the action ran with ``return_edits=ReturnEditsMode.ALL``). An action that needs approval
    is not applied yet: ``status`` is ``"pending_approval"``, ``approval_id`` names the request,
    and ``validation`` and ``edits`` are None. Both are None for an applied action."""


class BatchApplyActionResponse(Record):
    """``results`` (one per request) and ``edits``."""


class ValidateActionResponse(Record):
    """``result`` (VALID | INVALID), ``submission_criteria`` and ``parameters``."""
