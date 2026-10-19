"""Signed bunq transport. All credentials and resumable context live in 1Password."""
import base64
import fcntl
import json
import os
import subprocess
import uuid
from contextlib import contextmanager

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ITEM = os.environ.get("BUNQ_OP_ITEM_ID", "")
VAULT = os.environ.get("BUNQ_OP_VAULT_ID", "")
BASE = "https://api.bunq.com/v1"


class BunqError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


@contextmanager
def connection_lock():
    # Lock an existing operational file; no temporary credential/lock files.
    with open(__file__, "rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


class BunqClient:
    def __init__(self):
        self.state = {}
        self.api_key = None
        self.http = requests.Session()
        self.http.trust_env = False

    def load(self):
        if not ITEM or not VAULT:
            raise BunqError("Set BUNQ_OP_ITEM_ID and BUNQ_OP_VAULT_ID to the 1Password credential location")
        result = subprocess.run(
            ["op", "item", "get", ITEM, "--vault", VAULT, "--format=json"],
            capture_output=True, text=True, timeout=45,
        )
        if result.returncode:
            raise BunqError("1Password could not load the bunq credential")
        fields = {f.get("label"): f.get("value") for f in json.loads(result.stdout)["fields"]}
        self.api_key = fields["credential"]
        self.state = json.loads(fields.get("api_context") or "{}")
        if self.state.get("environment", "production") != "production":
            raise BunqError("Saved context environment does not match production")

    def save(self):
        result = subprocess.run(
            ["op", "item", "edit", ITEM, "--vault", VAULT,
             "api_context[concealed]=" + json.dumps(self.state, separators=(",", ":"))],
            capture_output=True, text=True, timeout=45,
        )
        if result.returncode:
            raise BunqError("Could not persist bunq signing context in 1Password; stopped before continuing")

    def request(self, method, path, token=None, body=None, query=None, signed=True,
                content_type=None, attachment_description=None):
        if not path.startswith("/") or ".." in path or "?" in path or "#" in path:
            raise BunqError("Invalid bunq operation path")
        data = body if isinstance(body, bytes) else json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode() if body is not None else b""
        headers = {
            "Content-Type": "application/json", "Accept": "application/json",
            "Cache-Control": "no-cache", "User-Agent": "bunq-banking-MCP/1.0",
            "X-Bunq-Language": "en_US", "X-Bunq-Region": "es_ES",
            "X-Bunq-Geolocation": "0 0 0 0 ES",
            "X-Bunq-Client-Request-Id": str(uuid.uuid4()),
        }
        if token:
            headers["X-Bunq-Client-Authentication"] = token
        if content_type:
            if content_type not in {"image/png", "image/jpeg", "image/gif"}:
                raise BunqError("Unsupported attachment content type")
            headers["Content-Type"] = content_type
        if attachment_description:
            if "\r" in attachment_description or "\n" in attachment_description:
                raise BunqError("Invalid attachment description")
            headers["X-Bunq-Attachment-Description"] = attachment_description
        if signed:
            private = serialization.load_pem_private_key(self.state["private_key"].encode(), password=None)
            headers["X-Bunq-Client-Signature"] = base64.b64encode(
                private.sign(data, padding.PKCS1v15(), hashes.SHA256())).decode()
        try:
            response = self.http.request(method, BASE + path, headers=headers,
                                         data=data if body is not None else None,
                                         params=query, timeout=40, allow_redirects=False)
        except requests.RequestException:
            raise BunqError("bunq network request failed; outcome unknown for writes") from None
        # bunq signs the raw response body. Verify whenever the server supplies a signature.
        signature = response.headers.get("X-Bunq-Server-Signature")
        if signature and self.state.get("server_public_key"):
            try:
                key = serialization.load_pem_public_key(self.state["server_public_key"].encode())
                key.verify(base64.b64decode(signature), response.content, padding.PKCS1v15(), hashes.SHA256())
            except Exception:
                raise BunqError("bunq response signature verification failed") from None
        try:
            payload = response.json()
        except ValueError:
            if response.ok:
                return {"content_type": response.headers.get("Content-Type"),
                        "encoding": "base64", "data": base64.b64encode(response.content).decode()}
            payload = {}
        if not response.ok:
            descriptions = [x.get("error_description", "") for x in payload.get("Error", [])]
            message = "; ".join(descriptions) or "bunq request rejected"
            # Never reflect credential material, even when a provider error echoes it.
            for value in (self.api_key, self.state.get("installation_token"), self.state.get("session_token")):
                if value:
                    message = message.replace(value, "[credential]")
            raise BunqError(f"HTTP {response.status_code}: {message}", response.status_code)
        return payload

    @staticmethod
    def find(payload, name, field):
        return next(row[name][field] for row in payload["Response"] if name in row)

    def connect(self):
        self.load()
        if self.state.get("pending"):
            raise BunqError("Previous bootstrap outcome is unknown for " + self.state["pending"] + "; reconcile provider registration before retrying")
        if not self.state.get("private_key"):
            private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            self.state = {
                "environment": "production",
                "private_key": private.private_bytes(serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode(),
                "public_key": private.public_key().public_bytes(serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo).decode(),
            }
            self.save()
        if not self.state.get("installation_token"):
            payload = self.bootstrap("installation", "/installation", body={"client_public_key": self.state["public_key"]}, signed=False)
            self.state["installation_token"] = self.find(payload, "Token", "token")
            self.state["server_public_key"] = self.find(payload, "ServerPublicKey", "server_public_key")
            self.save()
        if not self.state.get("device_id"):
            payload = self.bootstrap("device-server", "/device-server", self.state["installation_token"],
                {"description": "bunq banking MCP", "secret": self.api_key})
            self.state["device_id"] = self.find(payload, "Id", "id")
            self.save()
        if not self.state.get("session_token"):
            self.refresh_session()

    def bootstrap(self, phase, path, token=None, body=None, signed=True):
        self.state["pending"] = phase
        self.save()
        try:
            payload = self.request("POST", path, token, body, signed=signed)
        except BunqError as error:
            # Explicit client rejection proves the operation was not accepted.
            # Network/5xx errors keep the pending marker to prevent duplicate enrollment.
            if error.status and 400 <= error.status < 500:
                self.state.pop("pending", None)
                self.save()
            raise
        self.state.pop("pending", None)
        return payload

    def refresh_session(self):
        payload = self.request("POST", "/session-server", self.state["installation_token"], {"secret": self.api_key})
        self.state["session_token"] = self.find(payload, "Token", "token")
        users = [value for row in payload["Response"] for name, value in row.items() if name.startswith("User") and isinstance(value, dict) and "id" in value]
        if not users:
            raise BunqError("bunq session returned no authenticated user")
        self.state["user_id"] = users[0]["id"]
        self.state["user_type"] = next(name for row in payload["Response"] for name in row if name.startswith("User"))
        self.save()

    def call(self, method, path, query=None, body=None, content_type=None, attachment_description=None):
        try:
            return self.request(method, path, self.state["session_token"], body, query,
                                content_type=content_type, attachment_description=attachment_description)
        except BunqError as error:
            # Retry only reads after an explicit authentication rejection. Never replay writes.
            if error.status != 401 or method != "GET":
                raise
            self.refresh_session()
            return self.request(method, path, self.state["session_token"], body, query)
