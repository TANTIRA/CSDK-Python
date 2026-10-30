"""Where clauses and property references.

The server's where grammar is eq, gt, gte, lt, lte, range, regex, isNull,
and, or. It has no ``not``, no ``in`` and no "is not null", so ``~``,
``!=`` and ``is_null(False)`` raise, and ``in_`` becomes an ``or`` of
``eq``. and/or stay flat, because the server caps where depth at 5.
"""


class Where:
    """A where clause; ``&`` and ``|`` combine, ``~`` is refused."""

    def __init__(self, wire):
        self._wire = wire

    def __and__(self, other):
        return Where(join("and", [self._wire, clause(other)]))

    def __or__(self, other):
        return Where(join("or", [self._wire, clause(other)]))

    def __invert__(self):
        raise NotImplementedError(
            "~ (not) is not supported: this server's where clause has no `not` "
            "(eq, gt, gte, lt, lte, range, regex, isNull, and, or); use the opposite "
            "comparison instead")

    def __bool__(self):
        raise TypeError("combine where clauses with & and |, not `and` / `or`")

    def __repr__(self):
        return "Where(%r)" % (self._wire,)


def join(op, clauses):
    """One flat and/or: operands of the same op are merged."""
    conds = []
    for c in clauses:
        conds.extend(c["conditions"] if c.get("type") == op else [c])
    return conds[0] if len(conds) == 1 else {"type": op, "conditions": conds}


def clause(c):
    if isinstance(c, Where):
        return c._wire
    if isinstance(c, dict):
        return c
    raise TypeError("expected a where clause, got %r" % (c,))


class Property:
    """A property of an object type, to compare, sort or select by."""

    def __init__(self, wire):
        self._wire = wire

    def _cmp(self, op, value):
        return Where({"type": op, "property": self._wire, "value": value})

    def __eq__(self, v):
        return self._cmp("eq", v)

    def __ne__(self, v):
        raise NotImplementedError("!= is not supported: this server's where clause has no `not`")

    def __gt__(self, v):
        return self._cmp("gt", v)

    def __ge__(self, v):
        return self._cmp("gte", v)

    def __lt__(self, v):
        return self._cmp("lt", v)

    def __le__(self, v):
        return self._cmp("lte", v)

    __hash__ = None

    def in_(self, values):
        values = list(values)
        if not values:
            raise ValueError("in_() needs at least one value")
        return Where(join("or", [self._cmp("eq", v)._wire for v in values]))

    def range(self, lo, hi):
        return self._cmp("range", [lo, hi])

    def regex(self, pattern):
        return self._cmp("regex", pattern)

    def is_null(self, value=True):
        if not value:  # the server reads every isNull as "is null"
            raise NotImplementedError("is_null(False) (not null) is not supported by this API")
        return self._cmp("isNull", True)

    def asc(self):
        return {"property": self._wire, "direction": "asc"}

    def desc(self):
        return {"property": self._wire, "direction": "desc"}


def wire_prop(p):
    """A Property or a plain property name, as the wire name."""
    return p._wire if isinstance(p, Property) else p
