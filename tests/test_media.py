"""Media reference properties against a stub server: a typed object's media property, the
untyped reader, and upload."""
import json
import unittest

from converge_sdk import ConvergeClient
from converge_sdk.core import UserTokenAuth
from converge_sdk.ontologies import Media, Object, ObjectType, client_class

from .stub import Stub, ok

B = "/api/v2/ontologies/demo"
REF = {"mimeType": "image/png", "reference": {"type": "mediaSetViewItem", "mediaSetViewItem": {
    "mediaSetRid": "ri.mesta.main.media-set.photos", "mediaSetViewRid": "ri.mesta.main.media-set-view.photos",
    "mediaItemRid": "ri.mesta.main.media-item.1"}}}


class Order(Object):
    object_type = ObjectType("Order", "orderId", {"orderId": "orderId", "photo": "photo"}, media={"photo"})


Client = client_class("demo", {"Order": Order}, {})


def routes():
    obj = {"$rid": "order/o 1", "orderId": "o 1", "photo": json.dumps(REF)}  # the server may send JSON text
    return {
        ("POST", B + "/objects/Order/search"): ok({"data": [obj, {"$rid": "order/o2", "orderId": "o2"}],
                                                   "nextPageToken": None}),
        ("GET", B + "/objects/Order/order%2Fo%201"): ok(obj),
        ("GET", B + "/objects/Order/order%2Fo%201/media/photo/content"): ok(b"\x89PNG", 200, "image/png"),
        ("GET", B + "/objects/Order/order%2Fo%201/media/photo/metadata"):
            ok({"path": "a.png", "sizeBytes": 4, "mediaType": "image/png"}),
        ("POST", B + "/objectTypes/Order/media/photo/upload?mediaItemPath=dir%2Fa+b.png"): ok(REF),
        ("POST", B + "/objectTypes/Order/media/photo/upload"): ok(REF),
    }


class MediaTest(unittest.TestCase):
    def setUp(self):
        self.stub = Stub(routes())

    def tearDown(self):
        self.stub.close()

    def test_a_typed_media_property_reads_content_metadata_and_reference(self):
        c = Client(self.stub.base, auth=UserTokenAuth("t"))
        first, second = c.ontology.objects.Order.take(2)
        self.assertIsInstance(first.photo, Media)
        self.assertIsNone(second.photo)  # no value: no Media
        self.assertEqual(first.photo.get_media_reference(), REF)
        self.assertEqual(first.photo.get_media_content(), b"\x89PNG")
        m = first.photo.get_media_metadata()
        self.assertEqual((m.path, m.size_bytes, m.media_type), ("a.png", 4, "image/png"))
        self.assertEqual(first.raw["photo"], json.dumps(REF))  # the wire value is kept as is

    def test_untyped_get_and_upload(self):
        o = ConvergeClient(self.stub.base, token="t").ontology("demo")
        media = o.media.get("Order", "o 1", "photo")
        self.assertEqual(media.get_media_reference(), REF)
        self.assertEqual(media.get_media_content(), b"\x89PNG")
        self.assertEqual(o.media.upload("Order", "photo", b"abc", media_item_path="dir/a b.png"), REF)
        self.assertEqual(o.media.upload("Order", "photo", bytearray(b"x")), REF)
        with self.assertRaises(TypeError):
            o.media.upload("Order", "photo", "not bytes")
        uploads = [s for s in self.stub.seen if "/upload" in s[1]]
        self.assertEqual([(u[2]["Content-Type"], u[3]) for u in uploads],
                         [("application/octet-stream", b"abc"), ("application/octet-stream", b"x")])
        self.assertTrue(all(s[2]["Authorization"] == "Bearer t" for s in self.stub.seen))


if __name__ == "__main__":
    unittest.main()
