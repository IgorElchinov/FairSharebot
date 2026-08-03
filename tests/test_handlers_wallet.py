from __future__ import annotations

from fairsharebot.db import crypto_repo, users_repo
from fairsharebot.db.connection import get_connection
from fairsharebot.handlers.wallet import wallet_balance_command


async def test_walletbalance_refuses_when_chain_not_configured(settings, user_factory, chat_factory, update_factory):
    user = user_factory(1, username="alice")
    update, context = update_factory(user=user, chat=chat_factory(), text="/walletbalance")
    context.bot_data["settings"] = settings

    await wallet_balance_command(update, context)

    update.effective_message.reply_text.assert_awaited_once()
    assert "aren't configured" in update.effective_message.reply_text.call_args[0][0]


async def test_walletbalance_tells_user_they_have_no_wallet_yet(
    chain_settings, user_factory, chat_factory, update_factory, fake_chain_client
):
    user = user_factory(1, username="alice")
    update, context = update_factory(user=user, chat=chat_factory(), text="/walletbalance")
    context.bot_data["settings"] = chain_settings
    context.bot_data["chain_client"] = fake_chain_client

    with get_connection(chain_settings.db_path) as conn:
        users_repo.upsert_user(conn, user_id=1, username="alice", display_name="Alice")

    await wallet_balance_command(update, context)

    reply_text = update.effective_message.reply_text.call_args[0][0]
    assert "don't have a wallet yet" in reply_text


async def test_walletbalance_reports_custodial_wallet_with_native_balance(
    chain_settings, user_factory, chat_factory, update_factory, fake_chain_client
):
    user = user_factory(1, username="alice")
    update, context = update_factory(user=user, chat=chat_factory(), text="/walletbalance")
    context.bot_data["settings"] = chain_settings
    context.bot_data["chain_client"] = fake_chain_client

    with get_connection(chain_settings.db_path) as conn:
        users_repo.upsert_user(conn, user_id=1, username="alice", display_name="Alice")
        crypto_repo.upsert_wallet(conn, user_id=1, address="0xCustodialAddr", custody_type="custodial")

    fake_chain_client.token_balances["0xCustodialAddr"] = 5 * 10**18
    fake_chain_client.native_balances["0xCustodialAddr"] = 10**16

    await wallet_balance_command(update, context)

    reply_text = update.effective_message.reply_text.call_args[0][0]
    assert "0xCustodialAddr" in reply_text
    assert "custodial" in reply_text
    assert "Token balance: 5" in reply_text
    assert "Native ETH balance" in reply_text


async def test_walletbalance_external_wallet_omits_native_balance(
    chain_settings, user_factory, chat_factory, update_factory, fake_chain_client
):
    user = user_factory(1, username="alice")
    update, context = update_factory(user=user, chat=chat_factory(), text="/walletbalance")
    context.bot_data["settings"] = chain_settings
    context.bot_data["chain_client"] = fake_chain_client

    with get_connection(chain_settings.db_path) as conn:
        users_repo.upsert_user(conn, user_id=1, username="alice", display_name="Alice")
        crypto_repo.upsert_wallet(conn, user_id=1, address="0xExternalAddr", custody_type="external")

    fake_chain_client.token_balances["0xExternalAddr"] = 2 * 10**18

    await wallet_balance_command(update, context)

    reply_text = update.effective_message.reply_text.call_args[0][0]
    assert "external" in reply_text
    assert "Native ETH balance" not in reply_text
