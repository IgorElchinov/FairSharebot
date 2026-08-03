from __future__ import annotations

import logging

from fairsharebot.chain.wallets import get_or_create_custodial_wallet
from fairsharebot.db.connection import get_connection
from fairsharebot.db.users_repo import upsert_user
from fairsharebot.handlers.wallet import export_key_command

MNEMONIC = "test test test test test test test test test test test junk"


async def test_exportkey_refuses_when_chain_not_configured(settings, user_factory, chat_factory, update_factory):
    user = user_factory(1, username="alice")
    chat = chat_factory(chat_id=1, type_="private")
    update, context = update_factory(user=user, chat=chat, text="/exportkey")
    context.bot_data["settings"] = settings

    await export_key_command(update, context)

    reply_text = update.effective_message.reply_text.call_args[0][0]
    assert "aren't configured" in reply_text


async def test_exportkey_refuses_in_group_chat(chain_settings, user_factory, chat_factory, update_factory):
    user = user_factory(1, username="alice")
    group_chat = chat_factory(chat_id=100, type_="group")
    update, context = update_factory(user=user, chat=group_chat, text="/exportkey")
    context.bot_data["settings"] = chain_settings

    await export_key_command(update, context)

    reply_text = update.effective_message.reply_text.call_args[0][0]
    assert "private chat" in reply_text
    assert "0x" not in reply_text


async def test_exportkey_reports_no_custodial_wallet(chain_settings, user_factory, chat_factory, update_factory):
    user = user_factory(1, username="alice")
    dm_chat = chat_factory(chat_id=1, type_="private")
    update, context = update_factory(user=user, chat=dm_chat, text="/exportkey")
    context.bot_data["settings"] = chain_settings

    await export_key_command(update, context)

    reply_text = update.effective_message.reply_text.call_args[0][0]
    assert "don't have a custodial wallet" in reply_text


async def test_exportkey_returns_the_derived_private_key_in_dm(
    chain_settings, user_factory, chat_factory, update_factory
):
    user = user_factory(1, username="alice")
    dm_chat = chat_factory(chat_id=1, type_="private")

    with get_connection(chain_settings.db_path) as conn:
        upsert_user(conn, user_id=1, username="alice", display_name="Alice")
        wallet = get_or_create_custodial_wallet(conn, mnemonic=MNEMONIC, user_id=1)

    update, context = update_factory(user=user, chat=dm_chat, text="/exportkey")
    context.bot_data["settings"] = chain_settings

    await export_key_command(update, context)

    reply_text = update.effective_message.reply_text.call_args[0][0]
    assert reply_text.count("0x") >= 1
    assert "still re-derive" in reply_text
    assert wallet.address  # sanity: wallet was actually created


async def test_exportkey_never_writes_the_private_key_to_the_log(
    chain_settings, user_factory, chat_factory, update_factory, caplog
):
    """Regression guard: activity_log.reply()'s DEBUG-level logging must not
    leak a secret reply's contents, even under LOG_LEVEL=DEBUG."""
    user = user_factory(1, username="alice")
    dm_chat = chat_factory(chat_id=1, type_="private")

    with get_connection(chain_settings.db_path) as conn:
        upsert_user(conn, user_id=1, username="alice", display_name="Alice")
        get_or_create_custodial_wallet(conn, mnemonic=MNEMONIC, user_id=1)

    update, context = update_factory(user=user, chat=dm_chat, text="/exportkey")
    context.bot_data["settings"] = chain_settings

    with caplog.at_level(logging.DEBUG, logger="fairsharebot.activity"):
        await export_key_command(update, context)

    sent_text = update.effective_message.reply_text.call_args[0][0]
    private_key = sent_text.splitlines()[1]
    assert private_key.startswith("0x")
    assert all(private_key not in record.getMessage() for record in caplog.records)
