from __future__ import annotations

import os

import uvicorn

from ..config import ConfigError, load_settings
from .app import create_app


def main() -> None:
    try:
        settings = load_settings()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from None

    if settings.chain is None:
        raise SystemExit(
            "WALLET_MASTER_MNEMONIC and friends aren't set - this web app has "
            "nothing to serve without token mode configured."
        )

    from ..chain.client import Web3ChainClient

    chain_client = Web3ChainClient(
        rpc_url=settings.chain.rpc_url,
        token_address=settings.chain.token_address,
        settlement_address=settings.chain.settlement_address,
        relayer_private_key=settings.chain.relayer_private_key,
        owner_private_key=settings.chain.owner_private_key,
    )
    app = create_app(settings, chain_client)

    port = int(os.environ.get("WALLET_LINK_PORT", "8081"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
