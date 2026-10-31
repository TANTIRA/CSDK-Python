"""Where clauses and property references.

The server's where grammar is eq, gt, gte, lt, lte, range, regex, isNull,
and, or, not. ``~``, ``!=`` and ``is_null(False)`` become ``not``; ``== None``
is ``is_null()`` and ``!= None`` is ``is_null(False)``; ``starts_with`` is a
full-match regex; ``in_`` (the server has no ``in``) becomes an ``or`` of
``eq``. and/or stay flat and ``~~`` cancels, because the server caps where
depth at 5.
"""
import re


class Where:
    """A where clause; ``&``, ``|`` and ``~`` combine."""

    def __init__(self, wire):
        self._wire = wire

    def __and__(self, other):
        return Where(join("and", [self._wire, clause(other)]))

    def __or__(self, other):
        return Where(join("or", [self._wire, clause(other)]))

    def __invert__(self):
        if self._wire.get("type") == "not":
            return Where(self._wire["conditions"][0])
        return Where({"type": "not", "conditions": [self._wire]})

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
        return self.is_null() if v is None else self._cmp("eq", v)

    def __ne__(self, v):
        # not(eq): also true for an object with no value for the property
        return self.is_null(False) if v is None else ~self._cmp("eq", v)

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

    def starts_with(self, prefix):
        # a full-match regex on the server; [\s\S] so multi-line values match too
        return self._cmp("regex", re.sub(r"([.*+?^${}()|\[\]\\])", r"\\\1", str(prefix)) + "[\\s\\S]*")

    # Text search: whole words, case-insensitive, terms separated by whitespace or punctuation.
    def contains_any_term(self, terms):
        return self._cmp("containsAnyTerm", str(terms))

    def contains_all_terms(self, terms):
        return self._cmp("containsAllTerms", str(terms))

    def contains_all_terms_in_order(self, terms):
        """The terms as an adjacent phrase, in order."""
        return self._cmp("containsAllTermsInOrder", str(terms))

    def contains_all_terms_in_order_prefix_last_term(self, terms):
        """As contains_all_terms_in_order, the last term matching as a prefix."""
        return self._cmp("containsAllTermsInOrderPrefixLastTerm", str(terms))

    def is_null(self, value=True):
        # the server reads every isNull as "is null", so not-null is not(isNull)
        w = self._cmp("isNull", True)
        return w if value else ~w

    def asc(self):
        return {"property": self._wire, "direction": "asc"}

    def desc(self):
        return {"property": self._wire, "direction": "desc"}


def wire_prop(p):
    """A Property or a plain property name, as the wire name."""
    return p._wire if isinstance(p, Property) else p
