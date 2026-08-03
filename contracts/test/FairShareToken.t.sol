// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {FairShareToken} from "../src/FairShareToken.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

contract FairShareTokenTest is Test {
    FairShareToken token;
    address owner = makeAddr("owner");
    address alice = makeAddr("alice");

    function setUp() public {
        token = new FairShareToken(owner);
    }

    function test_ownerCanMint() public {
        vm.prank(owner);
        token.mint(alice, 100 ether);
        assertEq(token.balanceOf(alice), 100 ether);
    }

    function test_nonOwnerCannotMint() public {
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, alice));
        token.mint(alice, 100 ether);
    }

    function test_permitGrantsAllowanceWithoutOnChainApprove() public {
        (address holder, uint256 holderKey) = makeAddrAndKey("holder");
        address spender = makeAddr("spender");
        uint256 value = 42 ether;
        uint256 deadline = block.timestamp + 1 hours;

        bytes32 digest = keccak256(
            abi.encodePacked(
                "\x19\x01",
                token.DOMAIN_SEPARATOR(),
                keccak256(
                    abi.encode(
                        keccak256("Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)"),
                        holder,
                        spender,
                        value,
                        token.nonces(holder),
                        deadline
                    )
                )
            )
        );
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(holderKey, digest);

        // Anyone (e.g. the bot's relayer) can submit the permit on the holder's behalf.
        token.permit(holder, spender, value, deadline, v, r, s);

        assertEq(token.allowance(holder, spender), value);
        assertEq(token.nonces(holder), 1);
    }
}
