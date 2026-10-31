"""Object types, objects, object sets and linked objects."""
from ..core.transport import quote
from .media import Media, _reference
from .where import Property, clause, join, wire_prop


class Ontology:
    """One ontology on one transport, and the object classes by api name
    (a linked object comes back as its class when the client knows it)."""

    def __init__(self, transport, ontology_rid, classes=None):
        self.transport = transport
        self.rid = ontology_rid
        self.classes = dict(classes or {})  # api name -> Object subclass
        self.root = "/v2/ontologies"
        self.base = self.root + "/" + quote(ontology_rid)

    def request(self, method, path, body=None):
        return self.transport.request(method, self.base + path, body)


class GeoPoint(str):
    """A geopoint stored as ``"lat,lon"`` text: that text (so it compares and serialises as
    before), with ``latitude`` and ``longitude`` as floats. A geopoint the server sends as
    GeoJSON is left as sent."""

    def __new__(cls, latitude, longitude):
        lat, lon = float(latitude), float(longitude)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("a geopoint is latitude -90..90, longitude -180..180")
        self = super().__new__(cls, "%s,%s" % (latitude, longitude))
        self.latitude, self.longitude = lat, lon
        return self

    @classmethod
    def from_wire(cls, value):
        """``"lat,lon"`` -> GeoPoint; anything else (GeoJSON included) -> None."""
        if not isinstance(value, str) or value.strip()[:1] == "{":
            return None
        try:
            lat, lon = (x.strip() for x in value.split(","))
            return cls(lat, lon)
        except ValueError:
            return None

    def __getnewargs__(self):  # copy and pickle rebuild it from its own text
        return tuple(str(self).split(","))

    def __repr__(self):
        return "GeoPoint(latitude=%r, longitude=%r)" % (self.latitude, self.longitude)


class ObjectType:
    """``Type.object_type.<prop>`` gives a Property for where / order_by."""

    def __init__(self, api_name, primary_key, props, links=None, media=(), geo=()):
        self._api_name = api_name
        self._primary_key = primary_key
        self._props = props  # python name -> wire name
        self._links = links or {}  # link type -> linked object type api name
        self._media = frozenset(media)  # python names of media reference properties
        self._geo = frozenset(geo)  # python names of geopoint properties
        for py, wire in props.items():
            setattr(self, py, Property(wire))


class Object:
    """One object. A generated subclass sets ``object_type``; ``raw`` is the wire dict."""

    object_type = None

    def __init__(self, raw, ontology=None):
        self._raw = raw
        self.rid = raw.get("$rid")
        ot = self.object_type
        for py, wire in (ot._props.items() if ot else ()):
            value = raw.get(wire)
            if py in ot._media and value is not None and ontology is not None and self.rid:
                value = Media(ontology, ot._api_name, self.rid, wire, _reference(value))
            elif py in ot._geo and value is not None:
                value = GeoPoint.from_wire(value) or value  # an unreadable value stays as sent
            setattr(self, py, value)

    @property
    def raw(self):
        return self._raw

    def __getitem__(self, wire_name):
        return self._raw[wire_name]

    def __repr__(self):
        return "%s(%r)" % (type(self).__name__, self._raw)


class Page:
    def __init__(self, data, next_page_token, total_count=None):
        self.data = data
        self.next_page_token = next_page_token
        self.total_count = total_count


class Compute:
    def __init__(self, fn):
        self._fn = fn

    def compute(self):
        return self._fn()


def untyped_class(api_name, primary_key=None):
    """An Object subclass for a type known only by name (no generated code)."""
    return type(str(api_name), (Object,), {"object_type": ObjectType(api_name, primary_key, {})})


class ObjectSet:
    def __init__(self, ontology, cls, where=None, order=None, select=None):
        self._o = ontology
        self._cls = cls
        self._filter = where
        self._order = order
        self._select = select

    def _path(self, suffix=""):
        return "/objects/" + quote(self._cls.object_type._api_name) + suffix

    def where(self, *clauses):
        if not clauses:
            return self
        conds = ([self._filter] if self._filter else []) + [clause(c) for c in clauses]
        return ObjectSet(self._o, self._cls, join("and", conds), self._order, self._select)

    def order_by(self, order):
        """One property: ``Type.object_type.<p>.asc()`` / ``.desc()``."""
        if not (isinstance(order, dict) and set(order) == {"property", "direction"}
                and isinstance(order["property"], str) and order["direction"] in ("asc", "desc")):
            raise TypeError("order_by takes one property's .asc() or .desc()")
        return ObjectSet(self._o, self._cls, self._filter, order, self._select)

    def select(self, *properties):
        """Load only these properties (``Type.object_type.<p>`` or names); the rest come back None."""
        return ObjectSet(self._o, self._cls, self._filter, self._order,
                         [wire_prop(p) for p in properties])

    def page(self, page_size=None, page_token=None):
        body = {"pageSize": page_size or 50}
        if self._filter:
            body["where"] = self._filter
        if self._order:
            body["orderBy"] = self._order
        if page_token:
            body["pageToken"] = page_token
        if self._select is not None:
            body["select"] = self._select
        r = self._o.request("POST", self._path("/search"), body) or {}
        return Page([self._cls(o, self._o) for o in r.get("data") or []], r.get("nextPageToken"),
                    r.get("totalCount"))

    def iterate(self, page_size=None):
        token = None
        while True:
            p = self.page(page_size=page_size, page_token=token)
            for o in p.data:
                yield o
            token = p.next_page_token
            if not token:
                return

    def list(self, page_size=None):
        """Every object in the set, as a list (all pages: prefer iterate() or take() for big sets)."""
        return [o for o in self.iterate(page_size=page_size)]

    def take(self, n):
        out = []
        if n <= 0:
            return out
        for o in self.iterate(page_size=min(n, 1000)):
            out.append(o)
            if len(out) >= n:
                break
        return out

    def linked(self, primary_key, link_type):
        """The objects linked to one object ("c1" or "customer/c1") through link_type.

        A generated type knows its links (an unknown one is a ValueError); an
        untyped one sends any link name and the server answers."""
        links = self._cls.object_type._links
        target = links.get(link_type)
        if target is None and (links or self._cls.object_type._props):
            raise ValueError("%s has no link %r" % (self._cls.object_type._api_name, link_type))
        return LinkedObjects(self._o, self._path("/" + quote(bare_key(primary_key)) + "/links/"
                                                 + quote(link_type)),
                             self._o.classes.get(target))

    def get(self, primary_key):
        """One object by primary key ("c1") or by its $rid ("customer/c1", what GET takes)."""
        k = str(primary_key)
        if "/" not in k:
            k = self._cls.object_type._api_name.lower() + "/" + k
        return self._cls(self._o.request("GET", self._path("/" + quote(k))), self._o)

    def aggregate(self, type=None, field=None, group_by=None, metrics=None, order=None):
        """count | sum | avg | min | max | exactDistinct | approximateDistinct over this set.

        A group_by entry is a property, or ``{"field": p, "ranges": [[lo, hi], ...]}``
        / ``{"field": p, "fixedWidth": w}`` / ``duration(p, n, unit)`` / ``max_group_count(p, n)``.
        Instead of type and field, ``metrics=[metric("count"), metric("sum", p, "total")]``
        computes several at once; ``order=("total", "desc")`` orders the groups by one."""
        if metrics is None:
            agg = {"type": type or "count"}
        elif type is not None or field is not None:
            raise TypeError("aggregate: pass type/field or metrics, not both")
        else:
            agg = {"metrics": [{**m, "field": wire_prop(m["field"])} if m.get("field") is not None else dict(m)
                               for m in metrics]}
        if order is not None:
            name, direction = (order, "asc") if isinstance(order, str) else order
            agg["order"] = {"metric": name, "direction": direction}
        if self._filter:
            agg["where"] = self._filter
        if field is not None:
            agg["field"] = wire_prop(field)
        if group_by:
            agg["group_by"] = [{**g, "field": wire_prop(g["field"])} if isinstance(g, dict)
                               else wire_prop(g) for g in group_by]
        return self._o.request("POST", self._path("/aggregate"), {"aggregation": agg})

    def nearest_neighbors(self, query, num_neighbors, prop):
        """The num_neighbors objects of this set whose vector property is closest to query
        (exact cosine similarity, best first). The server's answer as a dict: ``data`` (objects
        with ``$score``) and ``skipped`` (readable objects with no comparable vector)."""
        body = {"property": wire_prop(prop), "numNeighbors": num_neighbors,
                "query": {"type": "vector", "value": list(query)}}
        if self._filter:
            body["where"] = self._filter
        return self._o.request("POST", self._path("/nearestNeighbors"), body)

    def count(self):
        def run():
            data = (self.aggregate("count") or {}).get("data") or []
            return int(float(data[0]["metrics"][0]["value"])) if data else 0
        return Compute(run)


def duration(prop, n, unit):
    """A date/time bucket group_by entry: n SECONDS | MINUTES | HOURS | DAYS | WEEKS | MONTHS |
    QUARTERS | YEARS, in UTC (weeks start on Monday)."""
    return {"field": prop, "duration": n, "unit": unit}


def max_group_count(prop, n):
    """An exact group_by entry keeping the n largest groups (the answer is then APPROXIMATE)."""
    return {"field": prop, "maxGroupCount": n}


def metric(type, field=None, name=None):
    """One metric for aggregate(metrics=...)."""
    m = {"type": type}
    if field is not None:
        m["field"] = field
    if name is not None:
        m["name"] = name
    return m


def bare_key(primary_key):
    """The link routes take the bare primary key: "c1" from "c1" or from the $rid "customer/c1"."""
    k = str(primary_key)
    return k.split("/", 1)[1] if "/" in k else k


class LinkedObjects:
    """Objects linked to one object through one link type, as the caller may read them."""

    def __init__(self, ontology, path, cls):
        self._o = ontology
        self._path = path
        self._cls = cls  # None: a linked type the client does not know comes back as a dict

    def _wrap(self, raw):
        return self._cls(raw, self._o) if self._cls else raw

    def page(self, page_size=None, page_token=None):
        q = "?pageSize=%d" % (page_size or 100)
        if page_token:
            q += "&pageToken=" + quote(page_token)
        r = self._o.request("GET", self._path + q) or {}
        return Page([self._wrap(o) for o in r.get("data") or []], r.get("nextPageToken"))

    def iterate(self, page_size=None):
        token = None
        while True:
            p = self.page(page_size=page_size or 1000, page_token=token)
            for o in p.data:
                yield o
            token = p.next_page_token
            if not token:
                return

    def get(self, primary_key):
        """One linked object; a ConvergeRPCError 404 when it is not linked."""
        return self._wrap(self._o.request("GET", self._path + "/" + quote(bare_key(primary_key))))
