<p align="center">
  <img src="assets/logo.png" alt="FairSharebot logo" width="120" height="120">
</p>

<h1 align="center">FairSharebot</h1>

<p align="center">
  A lightweight Telegram bot that splits shared trip expenses - no registration, no spreadsheets.
</p>

Add it to a group chat, start a trip, log payments as they happen, and close the trip when
you're done. FairSharebot (@fair_share_bot) works out the fewest payments needed to settle everyone up.

This project is vibe-coded. [See VIBECODING.md for more details.](vibecoding/VIBECODING.md)
The implementation plan lives in [vibecoding/PLAN.md](vibecoding/PLAN.md).

## Setup

Requires Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # or requirements.txt for a non-dev install

cp .env.example .env
# edit .env and set BOT_TOKEN to a token from @BotFather
```

Run it:

```bash
python -m fairsharebot
```

This starts the bot with long polling - no public URL or webhook needed. A SQLite database
is created automatically at `./data/fairsharebot.sqlite3` (configurable via `DB_PATH`).

Logs are written both to the console and to `./logs/fairsharebot.log` (configurable via
`LOG_DIR`), rotating at 5 MB with 5 backups kept. Check that file first if something goes
wrong - errors from handlers (including the full traceback) always land there.

Set `LOG_LEVEL=DEBUG` for a verbose mode useful while testing: every incoming message and
every reply gets logged with chat and user context (id, username, chat type/title), e.g.:

```
DEBUG fairsharebot.activity: <- chat_id=-100123 type=group title='Trip friends' | user_id=42 username=@alice name='Alice' | text='/pay 20 taxi for @bob'
DEBUG fairsharebot.activity: -> chat_id=-100123 type=group title='Trip friends' | user_id=42 username=@alice name='Alice' | reply='Recorded: 20.00 for taxi\nSplit equally among: Alice, Bob'
```

This only affects FairSharebot's own logger - `python-telegram-bot`'s transport-level DEBUG
logging (raw HTTP requests, the long-polling loop) stays suppressed regardless, since it fires
constantly whether or not anyone is actually using the bot and would drown out the useful
output.

## Usage

All commands operate on the chat's currently open trip - there's no trip ID to pass around,
since only one trip can be open per chat at a time.

| Command | Example | What it does |
|---|---|---|
| `/starttrip [name]` | `/starttrip Barcelona weekend` | Starts a trip in this chat |
| `/pay` (equal split) | `/pay 90 taxi for @alice @bob` | Payer = you; split evenly among you + mentions |
| `/pay` (exact amounts) | `/pay 90 dinner split me=30 @alice=30 @bob=30` | Amounts must sum to the total |
| `/pay` (weighted split) | `/pay 90 rent shares me=1 @alice=1 @bob=2` | Split proportionally to weights |
| `/cansel <id>` (or `/cancelpayment <id>`) | `/cansel 4` | Undoes a payment (see `/trip <id>` for payment ids) |
| `/balance` | `/balance` | Current balances + a live settlement preview |
| `/closetrip` | `/closetrip` | Closes the trip and posts the final settlement |
| `/trips` | `/trips` | Lists past trips in this chat, with totals |
| `/trip <id>` | `/trip 3` | Full breakdown and settlement for any trip |

Token-mode trips (only if the bot operator has configured crypto payments - see below):

| Command | Example | What it does |
|---|---|---|
| `/starttriptoken [name]` | `/starttriptoken Ski trip` | Starts a trip that settles automatically on-chain |
| `/pay` | (same grammar as above) | On a token trip, also pulls each participant's share on-chain immediately |
| `/walletbalance` | `/walletbalance` | Shows your linked wallet's token (and gas) balance |
| `/linkwallet` | `/linkwallet` | DMs you a link to connect your own wallet instead of the auto-created one |
| `/exportkey` | `/exportkey` (DM only) | Reveals your auto-created wallet's private key |
| `/minttoken` | `/minttoken @alice 100` | Operator-only: mints tokens to someone's wallet |

Tips:
- Reply to someone's message with `/pay` to include them without needing to `@mention` them.
- `me`/`@username` refer to yourself or a known chat member - exact and weighted splits can't
  reference someone who has no Telegram username *and* hasn't been `@mentioned`/replied to yet
  (there's no unambiguous way to write that as a `ref=value` token).
- Someone needs to have sent at least one message, been replied to, or been `@mentioned` in
  this chat before you can split a payment with them by `@username` - see the privacy mode
  note below if you want that to work from literally anyone's first message.

Run `/help` in the chat any time for the full command reference.

## Configuring the bot in BotFather

Message **@BotFather** to finish setting the bot up:

- `/setuserpic` - upload [`assets/logo.png`](assets/logo.png)
- `/setdescription` - paste [`assets/botfather/description.txt`](assets/botfather/description.txt)
<!-- - `/setshortdescription` - paste [`assets/botfather/short_description.txt`](assets/botfather/short_description.txt) -->
- `/setabouttext` - paste [`assets/botfather/about.txt`](assets/botfather/about.txt)
- `/setcommands` - paste [`assets/botfather/commands.txt`](assets/botfather/commands.txt) verbatim,
  so Telegram shows the `/` command menu with descriptions
- `/setprivacy` - **Disable**, so the bot can learn about chat members from any message, not
  just commands, replies to it, or `@mentions` of it. Without this, someone can only be
  `@username`-mentioned in a `/pay` after they've sent a command themselves.

## Token-mode trips (crypto payments)

FairSharebot can optionally settle a trip's splits with its own ERC-20 token on Base instead of
just tracking cash balances - each participant gets a wallet (created automatically, no setup
required) and `/pay` immediately pulls the right share on-chain via a standing allowance. This
is entirely opt-in per trip (`/starttriptoken` instead of `/starttrip`); cash trips are
completely unaffected and need none of the setup below.

### One-time setup

1. **Install [Foundry](https://book.getfoundry.sh/)** (`curl -L https://foundry.paradigm.xyz | bash && foundryup`) and deploy the contracts:
   ```bash
   cd contracts
   forge install   # lib/ isn't committed
   forge test      # 13 tests should pass
   OWNER_ADDRESS=0x... RELAYER_ADDRESS=0x... \
     forge script script/Deploy.s.sol --rpc-url base_sepolia --private-key $DEPLOYER_KEY --broadcast
   ./export_abi.sh   # copies the ABI into fairsharebot/chain/abi/
   ```
   This writes the deployed addresses to `deployments/base-sepolia.json`. `OWNER_ADDRESS` should
   ideally be a key you keep offline - it can mint tokens, rotate the relayer, and pause
   settlement, but never needs to be online day-to-day. `RELAYER_ADDRESS` is the bot's own hot
   wallet that pays gas for every settlement - fund it with a small amount of Base ETH.
2. **Set the chain env vars** in `.env` - see the commented-out block in `.env.example`
   (`WALLET_MASTER_MNEMONIC`, `RELAYER_PRIVATE_KEY`, `BASE_RPC_URL`, `CHAIN_ID`, `TOKEN_ADDRESS`,
   `SETTLEMENT_ADDRESS`, `OWNER_TELEGRAM_USER_ID`, `WALLET_LINK_BASE_URL`, optionally
   `OWNER_PRIVATE_KEY` for `/minttoken`). Leaving `WALLET_MASTER_MNEMONIC` unset keeps token mode
   entirely off - nothing else in this section is read in that case.
3. **Run the wallet-linking web app** (a separate process from the bot, so the two can be
   deployed/restarted independently): `python -m fairsharebot.webapp`. It listens on
   `WALLET_LINK_PORT` (default 8081) and needs a public HTTPS URL reverse-proxied to it -
   `WALLET_LINK_BASE_URL` must match wherever that ends up. `/linkwallet` DMs a link into this
   app, which is how a user swaps their auto-created wallet for one they control themselves.

### How it works, briefly

- Every user gets a **custodial wallet** automatically (derived from `WALLET_MASTER_MNEMONIC`,
  never stored - only its derivation index is). `/linkwallet` lets someone switch to a
  self-custodied wallet instead; `/exportkey` (DM only) reveals a custodial wallet's private key,
  though the bot can still re-derive that same key afterwards - true self-custody means moving
  funds to a *fresh* wallet and `/linkwallet`-ing that.
- Every wallet grants FairSharebot's `Settlement` contract a **standing max allowance** once
  (gaslessly, via an EIP-2612 `permit` signature) so the bot's relayer can pull funds on demand
  without asking again. This is the mechanism that makes settlement fully automated - and also
  the biggest concentration of risk in the whole design: a compromised relayer/owner key can
  drain any wallet up to its allowance. Keep custodial balances at "working capital for an
  active trip," not savings.
- `/pay` settles immediately; `/closetrip` is a safety net that nets whatever didn't actually
  confirm on-chain mid-trip (a revoked allowance, a stuck tx) and retries just the shortfall -
  see `fairsharebot/chain/settlement_service.py`'s module docstring-level comments for the exact
  residual math.
- 1 token = 1 real-world cent by fixed convention (`fairsharebot/chain/units.py`) - there's no
  exchange rate or real economic backing built in. Base Sepolia is the intended network for
  trying this out; treat any mainnet deployment as a separate, later decision (see the security
  notes in `fairsharebot/chain/settlement_service.py` and the contracts' `Pausable` circuit
  breaker first).

### Manual smoke test

With contracts deployed to Base Sepolia and both processes running (`python -m fairsharebot` and
`python -m fairsharebot.webapp`):

```
/starttriptoken Test trip
/minttoken @yourself 100        (as the OWNER_TELEGRAM_USER_ID user)
/pay 10 coffee for @someone
```
then check the transfer on [Basescan Sepolia](https://sepolia.basescan.org/), `/linkwallet` with
a real MetaMask to confirm the on-chain allowance lands, and `/closetrip` to see the residual
safety net run.

## Testing

```bash
pytest -q
```

No network access or real Telegram credentials are needed - handler tests construct `Update`
objects directly, and the settlement/parsing logic is tested as pure functions.

## Project layout

See [vibecoding/PLAN.md](vibecoding/PLAN.md) for the full architecture (data model, the
Telegram mention-resolution problem, the settlement algorithm, and the phased build order).

```
fairsharebot/
  __main__.py       # entrypoint: python -m fairsharebot
  config.py         # env-based settings (incl. optional ChainSettings for token mode)
  identity.py       # resolves @mentions/replies/text_mentions to known users
  settlement.py     # balance and settlement-transfer computation (cash)
  db/               # schema + repository layer (sqlite)
  handlers/         # one module per command, plus jobs.py (JobQueue)
  utils/            # /pay grammar parsing, message formatting
  chain/            # token mode: wallets, permit signing, chain client, settlement_service
  webapp/           # standalone /linkwallet signing-page web app (separate process)
contracts/          # FairShareToken + Settlement (Solidity, Foundry)
deployments/        # deployed contract addresses per network
tests/
```

## Known limitations / not yet built

- No reminders for who still owes money (planned; see `vibecoding/PLAN.md`).
- No receipt OCR, no multi-currency conversion.
- Settlement minimizes the transaction count with a greedy heuristic, not an exact solver
  (see the docstring in `fairsharebot/settlement.py` for why that's a reasonable tradeoff).
- Token mode: no capped/renewable allowance (standing max allowance only), no real economic
  backing for the token, and the master mnemonic/relayer key protection is sized for a small
  friends-group deployment, not audited for handling real value at scale - see the security
  notes in `fairsharebot/chain/settlement_service.py` before considering mainnet.
