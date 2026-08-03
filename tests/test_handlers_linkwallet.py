from __future__ import annotations

from unittest.mock import AsyncMock

from telegram.error import Forbidden

from fairsharebot.db import crypto_repo
from fairsharebot.db.connection import get_connection
from fairsharebot.handlers.wallet import link_wallet_command


async def test_linkwallet_refuses_when_chain_not_configured(settings, user_factory, chat_factory, update_factory):
    user = user_factory(1, username="alice")
    update, context = update_factory(user=user, chat=chat_factory(), text="/linkwallet")
    context.bot_data["settings"] = settings
    context.bot = AsyncMock()

    await link_wallet_command(update, context)

    context.bot.send_message.assert_not_called()
    reply_text = update.effective_message.reply_text.call_args[0][0]
    assert "aren't configured" in reply_text


async def test_linkwallet_dms_the_link_and_never_posts_it_in_group(
    chain_settings, user_factory, chat_factory, update_factory
):
    user = user_factory(1, username="alice")
    group_chat = chat_factory(chat_id=100, type_="group")
    update, context = update_factory(user=user, chat=group_chat, text="/linkwallet")
    context.bot_data["settings"] = chain_settings
    context.bot = AsyncMock()

    await link_wallet_command(update, context)

    context.bot.send_message.assert_awaited_once()
    dm_kwargs = context.bot.send_message.call_args.kwargs
    assert dm_kwargs["chat_id"] == user.id
    assert chain_settings.chain.link_base_url in dm_kwargs["text"]

    # The group reply must not contain the actual link - only a pointer to DM.
    group_reply = update.effective_message.reply_text.call_args[0][0]
    assert chain_settings.chain.link_base_url not in group_reply
    assert "DM" in group_reply


async def test_linkwallet_creates_a_pending_challenge(chain_settings, user_factory, chat_factory, update_factory):
    user = user_factory(1, username="alice")
    update, context = update_factory(user=user, chat=chat_factory(), text="/linkwallet")
    context.bot_data["settings"] = chain_settings
    context.bot = AsyncMock()

    await link_wallet_command(update, context)

    dm_text = context.bot.send_message.call_args.kwargs["text"]
    link = [line for line in dm_text.splitlines() if chain_settings.chain.link_base_url in line][0]
    token = link.rsplit("/", 1)[-1]

    with get_connection(chain_settings.db_path) as conn:
        challenge = crypto_repo.get_challenge(conn, token)

    assert challenge is not None
    assert challenge.telegram_user_id == 1
    assert challenge.status == "pending"


async def test_linkwallet_reports_when_it_cannot_dm_the_user(
    chain_settings, user_factory, chat_factory, update_factory
):
    user = user_factory(1, username="alice")
    update, context = update_factory(user=user, chat=chat_factory(), text="/linkwallet")
    context.bot_data["settings"] = chain_settings
    context.bot = AsyncMock()
    context.bot.send_message.side_effect = Forbidden("bot can't initiate conversation with a user")

    await link_wallet_command(update, context)

    reply_text = update.effective_message.reply_text.call_args[0][0]
    assert "/start" in reply_text
