"""Media reference properties: an object's property that names a media item.

The server checks both the object (visibility, markings, masking) and the media set before
it answers, so a Media only ever reads what the caller may read."""
import json
import types
import urllib.parse

from ..core.transport import parse, quote


def _reference(value):
    """A MediaReference dict, from the property value (a dict, or JSON text) or None."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    return value if isinstance(value, dict) else None


def _rid(object_type, primary_key):
    """What the object routes take: the $rid ("order/o1"), from a key or a $rid."""
    k = str(primary_key)
    return k if "/" in k else str(object_type).lower() + "/" + k


class Media:
    """One media reference property of one object."""

    def __init__(self, ontology, object_type, object_rid, prop, reference=None):
        self._o = ontology
        self._path = "/objects/%s/%s/media/%s" % (quote(object_type), quote(object_rid), quote(prop))
        self._reference = reference

    def get_media_content(self):
        """The bytes. Treat them as untrusted: never render them inline in a page of the API's origin."""
        t = self._o.transport
        return t.send("GET", t.base + self._o.base + self._path + "/content")

    def get_media_metadata(self):
        """``.path``, ``.size_bytes`` and ``.media_type``."""
        m = self._o.request("GET", self._path + "/metadata") or {}
        return types.SimpleNamespace(path=m.get("path"), size_bytes=m.get("sizeBytes"),
                                     media_type=m.get("mediaType"))

    def get_media_reference(self):
        """The MediaReference the property holds (``mimeType`` and ``reference``)."""
        return self._reference

    def __repr__(self):
        return "Media(%s)" % self._path


class MediaClient:
    """``client.ontology.media``: read a media property by object, or upload into one."""

    def __init__(self, ontology):
        self._o = ontology

    def get(self, object_type, primary_key, prop):
        """The media of one object's property ("o1" or "order/o1"); the reference is read with it."""
        rid = _rid(object_type, primary_key)
        obj = self._o.request("GET", "/objects/%s/%s" % (quote(object_type), quote(rid))) or {}
        return Media(self._o, object_type, rid, prop, _reference(obj.get(prop)))

    def upload(self, object_type, prop, data, media_item_path=None):
        """Upload bytes into the media set of a media property -> the MediaReference to pass to an
        action that writes the property."""
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("upload(object_type, prop, data): data must be bytes")
        t = self._o.transport
        url = t.base + self._o.base + "/objectTypes/%s/media/%s/upload" % (quote(object_type), quote(prop))
        if media_item_path is not None:
            url += "?" + urllib.parse.urlencode({"mediaItemPath": str(media_item_path)})
        return parse(t.send("POST", url, bytes(data), {"Content-Type": "application/octet-stream"}))
