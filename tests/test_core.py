import os
import tempfile
import unittest
from unittest import mock

from converge_sdk import ConfigError, ConvergeClient, ConvergeRPCError, UserTokenAuth
from converge_sdk.core.config import resolve

from .stub import Stub, ok

SECRET = "tok-secret-123"


class ConfigTest(unittest.TestCase):
    def test_arguments_then_environment_then_file(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve("h.example", SECRET), ("https://h.example", SECRET))
        env = {"CONVERGE_HOSTNAME": "http://e.example/api/", "CONVERGE_TOKEN": "env-tok"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(resolve(), ("http://e.example/api", "env-tok"))
        with mock.patch.dict(os.environ, {"CONVERGE_HOSTNAME": "e.example", "FOUNDRY_TOKEN": "f-tok"},
                             clear=True):
            self.assertEqual(resolve(), ("https://e.example", "f-tok"))  # FOUNDRY_TOKEN fallback
        with tempfile.NamedTemporaryFile("w", suffix=".cfg", delete=False) as f:
            f.write("[default]\nhostname = f.example\ntoken = file-tok\n")
        try:
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertEqual(resolve(config_file=f.name), ("https://f.example", "file-tok"))
        finally:
            os.unlink(f.name)

    def test_missing_values_name_what_is_missing_never_a_value(self):
        with mock.patch.dict(os.environ, {"CONVERGE_TOKEN": SECRET}, clear=True):
            with self.assertRaises(ConfigError) as e:
                resolve(config_file="/nonexistent/config")
        self.assertIn("hostname", str(e.exception))
        self.assertNotIn(SECRET, str(e.exception))


class TokenNeverShownTest(unittest.TestCase):
    def test_repr_str_and_errors_never_contain_the_token(self):
        stub = Stub({("GET", "/api/v2/datasets/ri.x"): ok({"message": "nope"}, 403)})
        try:
            client = ConvergeClient(stub.base, token=SECRET)
            with self.assertRaises(ConvergeRPCError) as e:
                client.datasets.get("ri.x")
        finally:
            stub.close()
        for text in (repr(client), str(client), repr(UserTokenAuth(SECRET)), str(UserTokenAuth(SECRET)),
                     str(e.exception), repr(e.exception), repr(client._transport)):
            self.assertNotIn(SECRET, text)
        self.assertEqual(e.exception.status, 403)
        self.assertEqual(stub.seen[0][2]["Authorization"], "Bearer " + SECRET)


class PlainHttpTest(unittest.TestCase):
    def test_a_token_is_never_sent_over_plain_http_except_to_localhost(self):
        for base in ("http://converge.example.com/api", "ftp://converge.example.com/api",
                     "http://127.0.0.1.evil.example/api", "http://localhost@evil.example/api"):
            with self.assertRaises(ConfigError) as e:
                ConvergeClient(base, token=SECRET)
            self.assertNotIn(SECRET, str(e.exception))
        for base in ("https://converge.example.com/api", "http://127.0.0.1:8080/api",
                     "http://localhost/api", "http://[::1]:9/api"):
            ConvergeClient(base, token=SECRET)  # accepted


class RedirectTest(unittest.TestCase):
    def test_a_redirect_is_refused_and_the_token_never_follows_it(self):
        elsewhere = Stub({("GET", "/steal"): ok({})})
        stub = Stub({("GET", "/api/v2/datasets/ri.x"): ok(("%s/steal" % elsewhere.base[:-4]).encode(), 302)})
        try:
            with self.assertRaises(ConvergeRPCError) as e:
                ConvergeClient(stub.base, token=SECRET).datasets.get("ri.x")
        finally:
            stub.close()
            elsewhere.close()
        self.assertEqual(e.exception.status, 302)
        self.assertEqual(elsewhere.seen, [])


if __name__ == "__main__":
    unittest.main()
