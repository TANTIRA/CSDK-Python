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


class TokenCheckTest(unittest.TestCase):
    def test_a_token_with_a_space_or_line_break_is_refused_without_echoing_it(self):
        stub = Stub({("GET", "/api/v2/datasets/ri.x"): ok({})})
        try:
            for bad in (SECRET + "\n", SECRET + "\r\nX-Evil: 1", "a b"):
                with self.assertRaises(ConfigError) as e:
                    ConvergeClient(stub.base, token=bad).datasets.get("ri.x")
                self.assertNotIn(SECRET, str(e.exception))
                self.assertIsInstance(e.exception, ValueError)
            self.assertEqual(stub.seen, [])
            # auth= takes a token or a callable as well as a UserTokenAuth; a callable runs per request
            n = iter(range(1, 9))
            c = ConvergeClient(stub.base, auth=lambda: "t%d" % next(n))
            c.datasets.get("ri.x")
            c.datasets.get("ri.x")
            ConvergeClient(stub.base, auth="t9").datasets.get("ri.x")
            self.assertEqual([h["Authorization"] for _, _, h, _ in stub.seen], ["Bearer t1", "Bearer t2", "Bearer t9"])
            self.assertIs(c.transport, c._transport)
        finally:
            stub.close()

    def test_userinfo_and_a_missing_host_are_refused(self):
        for base in ("https://user:pw@converge.example.com/api", "https://user@converge.example.com/api",
                     "https:///api", "http://"):
            with self.assertRaises(ConfigError) as e:
                ConvergeClient(base, token=SECRET)
            self.assertNotIn("pw", str(e.exception))
            self.assertNotIn(SECRET, str(e.exception))

    def test_a_broken_config_file_never_echoes_its_lines(self):
        with tempfile.NamedTemporaryFile("w", suffix=".cfg", delete=False) as f:
            f.write("token = %s\n[default]\nhostname = h.example\n" % SECRET)  # no section before the token
        try:
            with mock.patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ConfigError) as e:
                    resolve(config_file=f.name)
            self.assertNotIn(SECRET, str(e.exception))
        finally:
            os.unlink(f.name)


class RedirectBodyTest(unittest.TestCase):
    def test_a_refused_redirect_names_no_target_and_every_3xx_is_refused(self):
        stub = Stub({("GET", "/api/v2/datasets/ri.a"): ok(b"https://elsewhere.example/steal", 302),
                     ("GET", "/api/v2/datasets/ri.b"): ok({"errorName": "Moved"}, 300),
                     ("GET", "/api/v2/datasets/ri.c"): ok({"errorName": "Nope"}, 404)})
        try:
            c = ConvergeClient(stub.base, token=SECRET)
            for rid, status in (("ri.a", 302), ("ri.b", 300)):
                with self.assertRaises(ConvergeRPCError) as e:
                    c.datasets.get(rid)
                self.assertEqual((e.exception.status, e.exception.body), (status, "redirect refused"))
            with self.assertRaises(ConvergeRPCError) as e:
                c.datasets.get("ri.c")
            self.assertEqual((e.exception.error_name, e.exception.name), ("Nope", "Nope"))
        finally:
            stub.close()


if __name__ == "__main__":
    unittest.main()
