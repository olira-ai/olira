"""
Olira SDK — Patient Token

Patient tokens are short-lived JWTs (15 min) scoped to a single patient.
Use them when an AI agent or patient-facing device needs to call the Olira
MCP Patient State server — pass the token as a Bearer header. The client
never sees your API key.

When to use:
  - Agent session: mint per MCP session, pass as Bearer auth
  - Device/frontend: your backend mints on demand and forwards it
  - NOT for server-to-server: use your API key with sdk:state-read directly

Requires: sdk:patient-token scope
Run: python 07_patient_token.py <patient_id>
"""

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from olira import DEFAULT_BASE_URL, AuthError, OliraClient, OliraEnv  # noqa: E402

API_KEY = os.environ.get("OLIRA_API_KEY")
if not API_KEY:
    print("Error: OLIRA_API_KEY is not set.")
    print("  Copy examples/.env.example to examples/.env and fill in your API key.")
    raise SystemExit(1)

BASE_URL = os.environ.get("OLIRA_BASE_URL", DEFAULT_BASE_URL)
PATIENT_ID = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PATIENT_ID", "")

if not PATIENT_ID:
    print("Usage: python 07_patient_token.py <patient_id>")
    print("  Or set PATIENT_ID in your .env file.")
    raise SystemExit(1)

client = OliraClient(
    api_key=API_KEY,
    base_url=BASE_URL,
    environment=OliraEnv.DEVELOPMENT if "localhost" in BASE_URL else OliraEnv.PRODUCTION,
    async_flush=False,
)

try:
    # ── Mint a token ──────────────────────────────────────────────────────────────

    print(f"Minting patient token for {PATIENT_ID}")
    token = client.get_patient_token(patient_id=PATIENT_ID)

    print(f"  access_token: {token.access_token[:40]}…")
    print(f"  expires_in:   {token.expires_in}s ({token.expires_in // 60} min)")
    print(f"  token_type:   {token.token_type}")
    print(f"  scopes:       {token.scopes}")

    # ── Forwarding to an MCP client ───────────────────────────────────────────────
    #
    # Pass token.access_token as a Bearer header to the MCP Patient State server:
    #
    #   import httpx
    #   resp = httpx.post(
    #       "https://mcp.prod.olira.ai/mcp",
    #       headers={"Authorization": f"Bearer {token.access_token}"},
    #       json={"method": "get_view", "params": {"view_type": "weekly_health_summary"}},
    #   )

    # ── Session helper with automatic refresh ────────────────────────────────────
    #
    # Tokens expire after 15 minutes. Mint a fresh one for each session, or use a
    # helper like this to refresh automatically with a safety buffer.

    class PatientSession:
        """Caches a patient token and refreshes it 30 seconds before expiry."""

        def __init__(self, olira_client: OliraClient, patient_id: str) -> None:
            self._client = olira_client
            self._patient_id = patient_id
            self._token: str | None = None
            self._expires_at: float = 0.0

        def bearer(self) -> str:
            if time.time() >= self._expires_at - 30:
                tok = self._client.get_patient_token(patient_id=self._patient_id)
                self._token = tok.access_token
                self._expires_at = time.time() + tok.expires_in
                print(f"  [PatientSession] Token refreshed, valid for {tok.expires_in}s")
            return self._token  # type: ignore[return-value]

    session = PatientSession(client, PATIENT_ID)
    print(f"\nBearer (first call):  {session.bearer()[:40]}…")
    print(f"Bearer (cached call): {session.bearer()[:40]}…")  # no network call

    # ── Error handling ────────────────────────────────────────────────────────────

    try:
        client.get_patient_token(patient_id="not-a-valid-id")
    except AuthError as e:
        print(f"\nAuthError (invalid patient or missing scope): {e}")
    except Exception as e:  # noqa: BLE001
        print(f"\nError: {type(e).__name__}: {e}")

finally:
    client.close()
