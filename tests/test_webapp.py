from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

from fairsharebot.chain.wallets import derive_address, derive_private_key_hex
from fairsharebot.db import crypto_repo, users_repo
from fairsharebot.db.connection import get_connection
from fairsharebot.webapp import app as app_module
from fairsharebot.webapp.app import create_app

MNEMONIC = "test test test test test test test test test test test junk"
EXTERNAL_ADDRESS = derive_address(MNEMONIC, 500)
EXTERNAL_KEY = derive_private_key_hex(MNEMONIC, 500)


@pytest.fixture(autouse=True)
def _stub_notify(monkeypatch):
    """notify_user makes a real network call to api.telegram.org - stub it
    for every test in this module so the suite stays offline."""

    async def fake_notify(*args, **kwargs):
        fake_notify.calls.append(kwargs)

    fake_notify.calls = []
    monkeypatch.setattr(app_module, "notify_user", fake_notify)
    return fake_notify


@pytest.fixture
def client(chain_settings, fake_chain_client):
    app = create_app(chain_settings, fake_chain_client)
    with TestClient(app) as test_client:
        yield test_client


def _seed_challenge(db_path, *, user_id: int = 1, expired: bool = False) -> tuple[str, str]:
    with get_connection(db_path) as conn:
        users_repo.upsert_user(conn, user_id=user_id, username="alice", display_name="Alice")
        expires_at = datetime.now(timezone.utc) + (timedelta(minutes=-1) if expired else timedelta(minutes=15))
        nonce_message = f"Link this wallet to FairSharebot\nTelegram user: {user_id}\nNonce: abc123"
        crypto_repo.create_challenge(
            conn, token="tok123", user_id=user_id, nonce=nonce_message, expires_at=expires_at.isoformat()
        )
    return "tok123", nonce_message


def _sign_ownership(nonce_message: str) -> str:
    signed = Account.sign_message(encode_defunct(text=nonce_message), private_key=EXTERNAL_KEY)
    return signed.signature.hex()


def _sign_permit(typed_data: dict) -> str:
    signed = Account.sign_typed_data(EXTERNAL_KEY, full_message=typed_data)
    return signed.signature.hex()


def test_link_page_rejects_unknown_token(client):
    resp = client.get("/link/does-not-exist")
    assert resp.status_code == 410


def test_link_page_serves_html_for_valid_token(client, chain_settings):
    token, _ = _seed_challenge(chain_settings.db_path)
    resp = client.get(f"/link/{token}")
    assert resp.status_code == 200
    assert "Link your wallet" in resp.text


def test_challenge_endpoint_410s_when_expired(client, chain_settings):
    token, _ = _seed_challenge(chain_settings.db_path, expired=True)
    resp = client.get(f"/api/link/{token}")
    assert resp.status_code == 410


def test_full_link_flow_grants_allowance_and_upserts_wallet(client, chain_settings, fake_chain_client):
    token, nonce_message = _seed_challenge(chain_settings.db_path)

    challenge_resp = client.get(f"/api/link/{token}")
    assert challenge_resp.status_code == 200
    assert challenge_resp.json()["nonce_message"] == nonce_message

    typed_data_resp = client.get(f"/api/link/{token}/typed-data", params={"address": EXTERNAL_ADDRESS})
    assert typed_data_resp.status_code == 200
    typed_data = typed_data_resp.json()["typed_data"]

    ownership_sig = _sign_ownership(nonce_message)
    permit_sig = _sign_permit(typed_data)

    complete_resp = client.post(
        f"/api/link/{token}/complete",
        json={
            "address": EXTERNAL_ADDRESS,
            "ownership_signature": ownership_sig,
            "permit_signature": permit_sig,
        },
    )
    assert complete_resp.status_code == 200
    assert complete_resp.json()["status"] == "linked"

    with get_connection(chain_settings.db_path) as conn:
        wallet = crypto_repo.get_wallet(conn, 1)
        challenge = crypto_repo.get_challenge(conn, token)

    assert wallet.address == EXTERNAL_ADDRESS
    assert wallet.custody_type == "external"
    assert wallet.allowance_granted_at is not None
    assert challenge.status == "verified"
    assert len(fake_chain_client.permit_calls) == 1


def test_complete_rejects_ownership_signature_from_wrong_wallet(client, chain_settings):
    token, nonce_message = _seed_challenge(chain_settings.db_path)
    client.get(f"/api/link/{token}/typed-data", params={"address": EXTERNAL_ADDRESS})

    other_key = derive_private_key_hex(MNEMONIC, 501)
    bad_ownership_sig = Account.sign_message(encode_defunct(text=nonce_message), private_key=other_key).signature.hex()

    typed_data_resp = client.get(f"/api/link/{token}/typed-data", params={"address": EXTERNAL_ADDRESS})
    permit_sig = _sign_permit(typed_data_resp.json()["typed_data"])

    resp = client.post(
        f"/api/link/{token}/complete",
        json={"address": EXTERNAL_ADDRESS, "ownership_signature": bad_ownership_sig, "permit_signature": permit_sig},
    )
    assert resp.status_code == 400

    with get_connection(chain_settings.db_path) as conn:
        assert crypto_repo.get_wallet(conn, 1) is None


def test_complete_rejects_permit_signature_from_wrong_wallet(client, chain_settings):
    token, nonce_message = _seed_challenge(chain_settings.db_path)
    typed_data_resp = client.get(f"/api/link/{token}/typed-data", params={"address": EXTERNAL_ADDRESS})
    typed_data = typed_data_resp.json()["typed_data"]

    ownership_sig = _sign_ownership(nonce_message)
    other_key = derive_private_key_hex(MNEMONIC, 501)
    bad_permit_sig = Account.sign_typed_data(other_key, full_message=typed_data).signature.hex()

    resp = client.post(
        f"/api/link/{token}/complete",
        json={"address": EXTERNAL_ADDRESS, "ownership_signature": ownership_sig, "permit_signature": bad_permit_sig},
    )
    assert resp.status_code == 400

    with get_connection(chain_settings.db_path) as conn:
        assert crypto_repo.get_wallet(conn, 1) is None


def test_complete_without_fetching_typed_data_first_fails(client, chain_settings):
    token, nonce_message = _seed_challenge(chain_settings.db_path)
    ownership_sig = _sign_ownership(nonce_message)

    resp = client.post(
        f"/api/link/{token}/complete",
        json={"address": EXTERNAL_ADDRESS, "ownership_signature": ownership_sig, "permit_signature": "0x" + "00" * 65},
    )
    assert resp.status_code == 400


def test_complete_notifies_user_on_success(client, chain_settings, _stub_notify):
    token, nonce_message = _seed_challenge(chain_settings.db_path)
    typed_data = client.get(f"/api/link/{token}/typed-data", params={"address": EXTERNAL_ADDRESS}).json()["typed_data"]

    client.post(
        f"/api/link/{token}/complete",
        json={
            "address": EXTERNAL_ADDRESS,
            "ownership_signature": _sign_ownership(nonce_message),
            "permit_signature": _sign_permit(typed_data),
        },
    )

    assert len(_stub_notify.calls) == 1
    assert _stub_notify.calls[0]["telegram_user_id"] == 1
    assert _stub_notify.calls[0]["linked"] is True


def test_second_completion_attempt_is_rejected(client, chain_settings):
    token, nonce_message = _seed_challenge(chain_settings.db_path)
    typed_data = client.get(f"/api/link/{token}/typed-data", params={"address": EXTERNAL_ADDRESS}).json()["typed_data"]
    body = {
        "address": EXTERNAL_ADDRESS,
        "ownership_signature": _sign_ownership(nonce_message),
        "permit_signature": _sign_permit(typed_data),
    }
    first = client.post(f"/api/link/{token}/complete", json=body)
    assert first.status_code == 200

    second = client.post(f"/api/link/{token}/complete", json=body)
    assert second.status_code == 410
