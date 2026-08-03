from __future__ import annotations

import httpx


async def notify_user(bot_token: str, *, telegram_user_id: int, linked: bool, address: str) -> None:
    """Sends a DM directly via the Telegram Bot HTTP API, not through a live
    python-telegram-bot Application - this web app is a separate process from
    the bot (see plan decision #8), so it has no Application/JobQueue of its
    own to send through."""
    text = (
        f"Wallet linked: {address}\nYou're all set for token-mode trips."
        if linked
        else (
            f"Wallet verified for {address}, but the on-chain allowance transaction "
            "hasn't confirmed yet. It should shortly - no action needed."
        )
    )
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": telegram_user_id, "text": text},
            )
        except httpx.HTTPError:
            # Best-effort notification - the wallet is linked either way, and
            # /walletbalance lets the user check for themselves regardless.
            pass
