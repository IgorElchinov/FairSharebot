// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {FairShareToken} from "../src/FairShareToken.sol";
import {Settlement} from "../src/Settlement.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";

contract SettlementTest is Test {
    FairShareToken token;
    Settlement settlement;

    address owner = makeAddr("owner");
    address relayer = makeAddr("relayer");
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");
    address carol = makeAddr("carol");

    function setUp() public {
        token = new FairShareToken(owner);
        settlement = new Settlement(owner, token, relayer);

        vm.startPrank(owner);
        token.mint(alice, 1_000 ether);
        token.mint(bob, 1_000 ether);
        vm.stopPrank();

        vm.prank(alice);
        token.approve(address(settlement), type(uint256).max);
        vm.prank(bob);
        token.approve(address(settlement), type(uint256).max);
    }

    function _oneTransfer(address from, address to, uint256 amount) internal pure returns (Settlement.Transfer[] memory transfers) {
        transfers = new Settlement.Transfer[](1);
        transfers[0] = Settlement.Transfer({from: from, to: to, amount: amount});
    }

    function test_relayerCanSettleUsingExistingAllowance() public {
        vm.prank(relayer);
        settlement.settleBatch(_oneTransfer(alice, bob, 30 ether));

        assertEq(token.balanceOf(alice), 970 ether);
        assertEq(token.balanceOf(bob), 1_030 ether);
    }

    function test_settleBatchPullsMultipleTransfersAtomically() public {
        Settlement.Transfer[] memory transfers = new Settlement.Transfer[](2);
        transfers[0] = Settlement.Transfer({from: alice, to: carol, amount: 10 ether});
        transfers[1] = Settlement.Transfer({from: bob, to: carol, amount: 20 ether});

        vm.prank(relayer);
        settlement.settleBatch(transfers);

        assertEq(token.balanceOf(carol), 30 ether);
        assertEq(token.balanceOf(alice), 990 ether);
        assertEq(token.balanceOf(bob), 980 ether);
    }

    function test_wholeBatchRevertsIfOneTransferFailsInsufficientAllowance() public {
        // carol never approved the settlement contract.
        Settlement.Transfer[] memory transfers = new Settlement.Transfer[](2);
        transfers[0] = Settlement.Transfer({from: alice, to: bob, amount: 5 ether});
        transfers[1] = Settlement.Transfer({from: carol, to: bob, amount: 5 ether});

        vm.prank(relayer);
        vm.expectRevert();
        settlement.settleBatch(transfers);

        // alice's leg must not have applied either - atomic revert.
        assertEq(token.balanceOf(alice), 1_000 ether);
    }

    function test_wholeBatchRevertsIfOneTransferFailsInsufficientBalance() public {
        Settlement.Transfer[] memory transfers = new Settlement.Transfer[](2);
        transfers[0] = Settlement.Transfer({from: alice, to: bob, amount: 5 ether});
        transfers[1] = Settlement.Transfer({from: alice, to: bob, amount: 10_000 ether});

        vm.prank(relayer);
        vm.expectRevert();
        settlement.settleBatch(transfers);

        assertEq(token.balanceOf(alice), 1_000 ether);
    }

    function test_onlyRelayerCanCallSettleBatch() public {
        vm.prank(alice);
        vm.expectRevert(Settlement.NotRelayer.selector);
        settlement.settleBatch(_oneTransfer(alice, bob, 1 ether));
    }

    function test_ownerCanRotateRelayer() public {
        address newRelayer = makeAddr("newRelayer");

        vm.prank(owner);
        settlement.setRelayer(newRelayer);
        assertEq(settlement.relayer(), newRelayer);

        // Old relayer is now locked out.
        vm.prank(relayer);
        vm.expectRevert(Settlement.NotRelayer.selector);
        settlement.settleBatch(_oneTransfer(alice, bob, 1 ether));

        vm.prank(newRelayer);
        settlement.settleBatch(_oneTransfer(alice, bob, 1 ether));
        assertEq(token.balanceOf(bob), 1_001 ether);
    }

    function test_nonOwnerCannotRotateRelayer() public {
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, alice));
        settlement.setRelayer(alice);
    }

    function test_pausedBlocksSettlement() public {
        vm.prank(owner);
        settlement.pause();

        vm.prank(relayer);
        vm.expectRevert(Pausable.EnforcedPause.selector);
        settlement.settleBatch(_oneTransfer(alice, bob, 1 ether));
    }

    function test_ownerCanUnpause() public {
        vm.startPrank(owner);
        settlement.pause();
        settlement.unpause();
        vm.stopPrank();

        vm.prank(relayer);
        settlement.settleBatch(_oneTransfer(alice, bob, 1 ether));
        assertEq(token.balanceOf(bob), 1_001 ether);
    }

    function test_nonOwnerCannotPause() public {
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, alice));
        settlement.pause();
    }
}
