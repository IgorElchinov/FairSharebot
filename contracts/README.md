# FairSharebot contracts

`FairShareToken` (ERC-20 + EIP-2612 permit, mintable by the owner) and
`Settlement` (the only contract allowed to move tokens between users, via a
standing allowance each wallet grants it once). See `../vibecoding/PLAN.md`
and the project's crypto-payments plan for the full design.

## Setup

Dependencies (`lib/`) aren't committed — reinstall after cloning:

```
forge install
```

## Test

```
forge test
```

## Deploy

Requires `OWNER_ADDRESS` and `RELAYER_ADDRESS` env vars, and
`BASE_SEPOLIA_RPC_URL` for the `base_sepolia` RPC alias in `foundry.toml`.

```
forge script script/Deploy.s.sol \
  --rpc-url base_sepolia \
  --private-key $DEPLOYER_PRIVATE_KEY \
  --broadcast
```

Writes deployed addresses to `../deployments/base-sepolia.json` (override the
filename with `DEPLOY_NETWORK`).

## Export ABI

After changing a contract, re-run:

```
./export_abi.sh
```

This copies just the ABI (not full build artifacts) into
`../fairsharebot/chain/abi/`, which is what the Python bot actually ships.
