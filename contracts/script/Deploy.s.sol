// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {FairShareToken} from "../src/FairShareToken.sol";
import {Settlement} from "../src/Settlement.sol";

/// @notice Deploys FairShareToken + Settlement and records the addresses to
/// deployments/<network>.json so the Python bot can pick them up.
///
/// Usage (Base Sepolia):
///   forge script script/Deploy.s.sol \
///     --rpc-url base_sepolia \
///     --private-key $DEPLOYER_PRIVATE_KEY \
///     --broadcast
///
/// OWNER_ADDRESS and RELAYER_ADDRESS must be set in the environment.
/// DEPLOY_NETWORK controls the output filename (defaults to "base-sepolia").
contract Deploy is Script {
    function run() external {
        address owner = vm.envAddress("OWNER_ADDRESS");
        address relayer = vm.envAddress("RELAYER_ADDRESS");
        string memory network = vm.envOr("DEPLOY_NETWORK", string("base-sepolia"));

        vm.startBroadcast();
        FairShareToken token = new FairShareToken(owner);
        Settlement settlement = new Settlement(owner, token, relayer);
        vm.stopBroadcast();

        console.log("network         ", network);
        console.log("owner           ", owner);
        console.log("relayer         ", relayer);
        console.log("FairShareToken  ", address(token));
        console.log("Settlement      ", address(settlement));

        string memory key = "deployment";
        vm.serializeAddress(key, "FairShareToken", address(token));
        vm.serializeAddress(key, "Settlement", address(settlement));
        vm.serializeAddress(key, "owner", owner);
        string memory finalJson = vm.serializeAddress(key, "relayer", relayer);

        vm.writeJson(finalJson, string.concat("../deployments/", network, ".json"));
    }
}
