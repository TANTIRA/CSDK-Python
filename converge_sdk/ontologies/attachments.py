"""Attachments: outside the ontology path, at /v2/ontologies/attachments."""
import re
import secrets

from ..core.transport import parse, quote

# the server's media type grammar: no line break can add a header
_MEDIA_TYPE = re.compile(r"[a-z0-9][a-z0-9!#$&^_.+-]{0,126}/[a-z0-9][a-z0-9!#$&^_.+-]{0,126}")


class Attachments:
    def __init__(self, ontology):
        self._t = ontology.transport
        self._url = ontology.transport.base + ontology.root + "/attachments"

    def upload(self, data, filename, media_type="application/octet-stream"):
        """Upload bytes; pass the returned rid as an attachment parameter of an action."""
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("upload(data, filename): data must be bytes")
        if not _MEDIA_TYPE.fullmatch(str(media_type)):
            raise ValueError("upload: media_type must look like type/subtype")
        # the filename goes into a multipart header: no quote or line break may end it early
        name = "".join("_" if c in '"\\\r\n' else c for c in str(filename)) or "unnamed"
        bnd = "csdk" + secrets.token_hex(16)
        body = ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
                "Content-Type: %s\r\n\r\n" % (bnd, name, media_type)).encode() + bytes(data) \
            + ("\r\n--%s--\r\n" % bnd).encode()
        return parse(self._t.send("POST", self._url + "/upload", body,
                                  {"Content-Type": "multipart/form-data; boundary=" + bnd}))

    def get(self, rid):
        return parse(self._t.send("GET", self._url + "/" + quote(rid)))

    def read(self, rid):
        """The bytes; readable when you uploaded it or can read an object that references it."""
        return self._t.send("GET", self._url + "/" + quote(rid) + "/content")
