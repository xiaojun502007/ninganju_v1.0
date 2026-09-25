import json
import hashlib
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import error, request
from unittest.mock import patch

from server import api_server


class PasswordChangeTests(unittest.TestCase):
    def test_change_password_requires_current_password_and_persists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(api_server, "DB_PATH", Path(temp_dir) / "auth.db"):
                api_server.init_db()
                # Existing installations use the previous salted SHA-256 format.
                with api_server.get_connection() as conn:
                    legacy_hash = hashlib.sha256(b"ninganju-demo-user:12345678").hexdigest()
                    conn.execute(
                        "update users set password_hash = ? where username = ?",
                        (legacy_hash, "xiaoning"),
                    )
                server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.NinganjuHandler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    base_url = f"http://127.0.0.1:{server.server_port}"

                    def post(path, data):
                        payload = json.dumps(data).encode("utf-8")
                        http_request = request.Request(
                            base_url + path,
                            payload,
                            {"Content-Type": "application/json"},
                            method="POST",
                        )
                        try:
                            with request.urlopen(http_request) as response:
                                return response.status, json.load(response)
                        except error.HTTPError as response:
                            with response:
                                return response.code, json.load(response)

                    account = {"username": "xiaoning", "currentPassword": "12345678"}
                    status, _ = post("/api/change-password", {
                        **account, "currentPassword": "wrong-password",
                        "newPassword": "new-password-123", "confirmPassword": "new-password-123",
                    })
                    self.assertEqual(status, 401)

                    status, result = post("/api/change-password", {
                        **account, "newPassword": "new-password-123",
                        "confirmPassword": "new-password-123",
                    })
                    self.assertEqual(status, 200)
                    self.assertTrue(result["ok"])

                    api_server.init_db()
                    old_status, _ = post("/api/login", {"username": "xiaoning", "password": "12345678"})
                    new_status, _ = post("/api/login", {"username": "xiaoning", "password": "new-password-123"})
                    self.assertEqual(old_status, 401)
                    self.assertEqual(new_status, 200)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
