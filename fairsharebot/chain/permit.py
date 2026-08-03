from __future__ import annotations

from eth_account import Account
from eth_account.datastructures import SignedMessage
from eth_account.messages import encode_defunct, encode_typed_data
from eth_utils import to_checksum_address

MAX_UINT256 = 2**256 - 1

# Must match FairShareToken's constructor args exactly (name passed to
# ERC20Permit, OpenZeppelin's fixed EIP712 version "1") - a mismatch here
# means the recovered signer never matches, and permit() reverts on-chain
# with "ERC2612InvalidSigner" rather than failing loudly in Python.
TOKEN_NAME = "FairShare Token"
EIP712_VERSION = "1"


def build_permit_typed_data(
    *, token_address: str, chain_id: int, owner: str, spender: str, value: int, nonce: int, deadline: int
) -> dict:
    """EIP-712 typed data for FairShareToken's permit. Both the custodial
    signing path (below) and the /linkwallet browser page - which builds the
    equivalent structure for the user's own wallet to sign - must produce
    this exact structure, or the two signatures recover to different
    addresses than intended.

    Addresses are checksummed here rather than trusted from the caller -
    eth_abi's EIP-712 encoder rejects a syntactically valid but non-checksum
    address outright, and env-var-sourced addresses (TOKEN_ADDRESS,
    SETTLEMENT_ADDRESS) can easily arrive in whatever case someone pasted."""
    return {
        "domain": {
            "name": TOKEN_NAME,
            "version": EIP712_VERSION,
            "chainId": chain_id,
            "verifyingContract": to_checksum_address(token_address),
        },
        "primaryType": "Permit",
        "types": {
            "Permit": [
                {"name": "owner", "type": "address"},
                {"name": "spender", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "nonce", "type": "uint256"},
                {"name": "deadline", "type": "uint256"},
            ],
        },
        "message": {
            "owner": to_checksum_address(owner),
            "spender": to_checksum_address(spender),
            "value": value,
            "nonce": nonce,
            "deadline": deadline,
        },
    }


def sign_permit_with_key(private_key: str, typed_data: dict) -> tuple[int, bytes, bytes]:
    """Custodial path: the bot signs invisibly with the re-derived key - no
    user interaction. Returns (v, r, s) ready for Settlement/token.permit()."""
    signed: SignedMessage = Account.sign_typed_data(private_key, full_message=typed_data)
    return signed.v, signed.r.to_bytes(32, "big"), signed.s.to_bytes(32, "big")


def recover_permit_signer(typed_data: dict, *, v: int, r: bytes, s: bytes) -> str:
    """External-wallet path: verifies a signature that came back from the
    /linkwallet browser page actually belongs to the address it claims to,
    before the bot ever relays it on-chain."""
    signable = encode_typed_data(full_message=typed_data)
    signature = r + s + bytes([v])
    return Account.recover_message(signable, signature=signature)


def recover_ownership_signer(nonce_message: str, *, signature: bytes) -> str:
    """Verifies the plain-text ownership-proof signature (not EIP-712) from
    the /linkwallet challenge flow."""
    signable = encode_defunct(text=nonce_message)
    return Account.recover_message(signable, signature=signature)
