import unittest
from unittest.mock import Mock

from client import BunqError
from server import readback


class ReadbackTests(unittest.TestCase):
    def test_created_note_uses_native_get(self):
        c = Mock()
        c.call.return_value = {"Response": [{"NoteText": {"id": 3}}]}
        result = readback(c, {"method": "POST", "path": "/user/42/monetary-account/1/payment/2/note-text"},
                          {"Response": [{"Id": {"id": 3}}]})
        self.assertTrue(result["read_completed"])
        c.call.assert_called_once_with("GET", "/user/42/monetary-account/1/payment/2/note-text/3")

    def test_delete_is_verified_on_404(self):
        c = Mock()
        c.call.side_effect = BunqError("Not found", 404)
        result = readback(c, {"method": "DELETE", "path": "/user/42/monetary-account/1/payment/2/note-text/3"}, {})
        self.assertTrue(result["deletion_verified"])

    def test_missing_get_does_not_claim_verification(self):
        c = Mock()
        result = readback(c, {"method": "POST", "path": "/no-modeled-path"}, {})
        self.assertFalse(result["verified"])
        c.call.assert_not_called()
