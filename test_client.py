import base64
import unittest
from unittest.mock import Mock

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from client import BunqClient, BunqError


class TransportTests(unittest.TestCase):
    def client(self):
        c = BunqClient()
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        c.state = {
            "private_key": private.private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode(),
            "server_public_key": private.public_key().public_bytes(serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo).decode(),
            "session_token": "old-token",
        }
        c.http = Mock()
        return c, private

    def test_signs_exact_bytes_and_verifies_response(self):
        c, private = self.client()
        raw = b'{"Response":[]}'
        response = Mock(ok=True, content=raw, headers={"X-Bunq-Server-Signature": base64.b64encode(
            private.sign(raw, padding.PKCS1v15(), hashes.SHA256())).decode()})
        response.json.return_value = {"Response": []}
        c.http.request.return_value = response
        c.request("POST", "/example", "token", {"text": "Espa\u00f1a"})
        kwargs = c.http.request.call_args.kwargs
        private.public_key().verify(base64.b64decode(kwargs["headers"]["X-Bunq-Client-Signature"]),
                                    kwargs["data"], padding.PKCS1v15(), hashes.SHA256())
        self.assertFalse(kwargs["allow_redirects"])

    def test_rejects_tampered_response(self):
        c, _ = self.client()
        c.http.request.return_value = Mock(content=b'changed', headers={"X-Bunq-Server-Signature": "AAAA"})
        with self.assertRaisesRegex(BunqError, "signature verification"):
            c.request("GET", "/user/1")

    def test_upload_signs_raw_bytes(self):
        c, private = self.client()
        response = Mock(ok=True, content=b'{}', headers={})
        response.json.return_value = {}
        c.http.request.return_value = response
        raw = b'\x89PNG\r\n\x1a\nimage'
        c.request("POST", "/attachment-public", "token", raw,
                  content_type="image/png", attachment_description="Receipt")
        kwargs = c.http.request.call_args.kwargs
        self.assertEqual(kwargs["data"], raw)
        self.assertEqual(kwargs["headers"]["Content-Type"], "image/png")
        self.assertEqual(kwargs["headers"]["X-Bunq-Attachment-Description"], "Receipt")
        private.public_key().verify(base64.b64decode(kwargs["headers"]["X-Bunq-Client-Signature"]),
                                    raw, padding.PKCS1v15(), hashes.SHA256())

    def test_does_not_replay_mutations(self):
        c, _ = self.client()
        c.request = Mock(side_effect=BunqError("Unauthorized", 401))
        c.refresh_session = Mock()
        with self.assertRaises(BunqError):
            c.call("POST", "/user/1/note", body={})
        c.refresh_session.assert_not_called()
        self.assertEqual(c.request.call_count, 1)

    def test_read_refresh_replaces_token(self):
        c, _ = self.client()
        c.request = Mock(side_effect=[BunqError("Unauthorized", 401), {"Response": []}])
        c.refresh_session = Mock(side_effect=lambda: c.state.update(session_token="new-token"))
        c.call("GET", "/user/1")
        self.assertEqual(c.request.call_args.args[2], "new-token")


if __name__ == "__main__":
    unittest.main()
