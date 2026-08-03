from __future__ import annotations

from fairsharebot.db import crypto_repo, users_repo
from fairsharebot.db.connection import get_connection
from fairsharebot.handlers.admin import mint_token_command

OWNER_ID = 999  # matches chain_settings fixture's owner_telegram_user_id


def _make_user(conn, user_id: int, username: str, *, chat_id: int = 100) -> None:
    users_repo.upsert_user(conn, user_id=user_id, username=username, display_name=username.title())
    users_repo.upsert_chat_user(conn, chat_id=chat_id, user_id=user_id)


async def test_minttoken_refuses_when_chain_not_configured(settings, user_factory, chat_factory, update_factory):
    user = user_factory(OWNER_ID, username="owner")
    update, context = update_factory(user=user, chat=chat_factory(), args=["@alice", "100"])
    context.bot_data["settings"] = settings

    await mint_token_command(update, context)

    reply_text = update.effective_message.reply_text.call_args[0][0]
    assert "aren't configured" in reply_text


async def test_minttoken_refuses_non_owner(chain_settings, user_factory, chat_factory, update_factory, fake_chain_client):
    user = user_factory(1, username="notowner")
    update, context = update_factory(user=user, chat=chat_factory(), args=["@alice", "100"])
    context.bot_data["settings"] = chain_settings
    context.bot_data["chain_client"] = fake_chain_client

    await mint_token_command(update, context)

    reply_text = update.effective_message.reply_text.call_args[0][0]
    assert "Only the bot operator" in reply_text
    assert fake_chain_client.mint_calls == []


async def test_minttoken_rejects_bad_usage(chain_settings, user_factory, chat_factory, update_factory, fake_chain_client):
    owner = user_factory(OWNER_ID, username="owner")
    update, context = update_factory(user=owner, chat=chat_factory(), args=["@alice"])
    context.bot_data["settings"] = chain_settings
    context.bot_data["chain_client"] = fake_chain_client

    await mint_token_command(update, context)

    reply_text = update.effective_message.reply_text.call_args[0][0]
    assert "Usage" in reply_text


async def test_minttoken_rejects_invalid_amount(chain_settings, user_factory, chat_factory, update_factory, fake_chain_client):
    owner = user_factory(OWNER_ID, username="owner")
    update, context = update_factory(user=owner, chat=chat_factory(), args=["@alice", "-5"])
    context.bot_data["settings"] = chain_settings
    context.bot_data["chain_client"] = fake_chain_client

    await mint_token_command(update, context)

    reply_text = update.effective_message.reply_text.call_args[0][0]
    assert "positive" in reply_text
    assert fake_chain_client.mint_calls == []


async def test_minttoken_mints_to_resolved_users_wallet(
    chain_settings, user_factory, chat_factory, update_factory, fake_chain_client
):
    owner = user_factory(OWNER_ID, username="owner")
    chat = chat_factory(100)

    with get_connection(chain_settings.db_path) as conn:
        _make_user(conn, 42, "alice")

    update, context = update_factory(user=owner, chat=chat, args=["@alice", "100"])
    context.bot_data["settings"] = chain_settings
    context.bot_data["chain_client"] = fake_chain_client

    await mint_token_command(update, context)

    with get_connection(chain_settings.db_path) as conn:
        wallet = crypto_repo.get_wallet(conn, 42)

    assert wallet is not None
    assert wallet.custody_type == "custodial"
    assert len(fake_chain_client.mint_calls) == 1
    assert fake_chain_client.mint_calls[0] == (wallet.address, 100 * 10**18)

    reply_text = update.effective_message.reply_text.call_args[0][0]
    assert "Minted" in reply_text
    assert wallet.address in reply_text


async def test_minttoken_reports_unknown_user(chain_settings, user_factory, chat_factory, update_factory, fake_chain_client):
    owner = user_factory(OWNER_ID, username="owner")
    update, context = update_factory(user=owner, chat=chat_factory(), args=["@nobody", "100"])
    context.bot_data["settings"] = chain_settings
    context.bot_data["chain_client"] = fake_chain_client

    await mint_token_command(update, context)

    reply_text = update.effective_message.reply_text.call_args[0][0]
    assert "don't know who" in reply_text
    assert fake_chain_client.mint_calls == []


async def test_minttoken_unknown_user_message_does_not_double_up_the_at_sign(
    chain_settings, user_factory, chat_factory, update_factory, fake_chain_client
):
    """Regression test: resolve_ref/UnknownUserError carry the ref as given -
    if the handler doesn't strip a leading '@' before resolving, the error
    reply ends up reading '@@nobody' instead of '@nobody'."""
    owner = user_factory(OWNER_ID, username="owner")
    update, context = update_factory(user=owner, chat=chat_factory(), args=["@nobody", "100"])
    context.bot_data["settings"] = chain_settings
    context.bot_data["chain_client"] = fake_chain_client

    await mint_token_command(update, context)

    reply_text = update.effective_message.reply_text.call_args[0][0]
    assert "@@nobody" not in reply_text
    assert "@nobody" in reply_text


async def test_minttoken_accepts_me_as_a_ref(chain_settings, user_factory, chat_factory, update_factory, fake_chain_client):
    owner = user_factory(OWNER_ID, username="owner")
    update, context = update_factory(user=owner, chat=chat_factory(), args=["me", "50"])
    context.bot_data["settings"] = chain_settings
    context.bot_data["chain_client"] = fake_chain_client

    await mint_token_command(update, context)

    with get_connection(chain_settings.db_path) as conn:
        wallet = crypto_repo.get_wallet(conn, OWNER_ID)

    assert wallet is not None
    assert len(fake_chain_client.mint_calls) == 1
