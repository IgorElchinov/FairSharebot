from __future__ import annotations

from eth_account import Account
from eth_account.messages import encode_defunct

from fairsharebot.chain.permit import (
    MAX_UINT256,
    build_permit_typed_data,
    recover_ownership_signer,
    recover_permit_signer,
    sign_permit_with_key,
)
from fairsharebot.chain.wallets import derive_address, derive_private_key_hex

MNEMONIC = "test test test test test test test test test test test junk"
OWNER_ADDRESS = derive_address(MNEMONIC, 1)
OWNER_KEY = derive_private_key_hex(MNEMONIC, 1)
# EIP-712 address encoding requires a valid EIP-55 checksum, so these borrow
# real derived addresses rather than hand-typed placeholders.
SPENDER = derive_address(MNEMONIC, 2)
TOKEN_ADDRESS = derive_address(MNEMONIC, 3)


def _typed_data(nonce: int = 0, deadline: int = 9999999999, value: int = MAX_UINT256) -> dict:
    return build_permit_typed_data(
        token_address=TOKEN_ADDRESS,
        chain_id=31337,
        owner=OWNER_ADDRESS,
        spender=SPENDER,
        value=value,
        nonce=nonce,
        deadline=deadline,
    )


def test_sign_and_recover_permit_round_trips_to_owner():
    typed_data = _typed_data()
    v, r, s = sign_permit_with_key(OWNER_KEY, typed_data)

    recovered = recover_permit_signer(typed_data, v=v, r=r, s=s)

    assert recovered.lower() == OWNER_ADDRESS.lower()


def test_recover_permit_fails_for_tampered_value():
    typed_data = _typed_data(value=1000)
    v, r, s = sign_permit_with_key(OWNER_KEY, typed_data)

    tampered = _typed_data(value=999999)
    recovered = recover_permit_signer(tampered, v=v, r=r, s=s)

    assert recovered.lower() != OWNER_ADDRESS.lower()


def test_recover_permit_fails_for_different_nonce():
    typed_data = _typed_data(nonce=0)
    v, r, s = sign_permit_with_key(OWNER_KEY, typed_data)

    tampered = _typed_data(nonce=1)
    recovered = recover_permit_signer(tampered, v=v, r=r, s=s)

    assert recovered.lower() != OWNER_ADDRESS.lower()


def test_recover_ownership_signer_round_trips():
    message = "link-telegram-user-42:some-nonce-value"
    signed = Account.sign_message(encode_defunct(text=message), private_key=OWNER_KEY)

    recovered = recover_ownership_signer(message, signature=signed.signature)

    assert recovered.lower() == OWNER_ADDRESS.lower()


def test_recover_ownership_signer_fails_for_wrong_message():
    message = "link-telegram-user-42:some-nonce-value"
    signed = Account.sign_message(encode_defunct(text=message), private_key=OWNER_KEY)

    recovered = recover_ownership_signer("a different message entirely", signature=signed.signature)

    assert recovered.lower() != OWNER_ADDRESS.lower()
