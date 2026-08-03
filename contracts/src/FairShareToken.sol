// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {ERC20Permit} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20Permit.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/// @notice FairSharebot's own ERC-20, mintable by the operator and using
/// EIP-2612 permit so wallet <-> Settlement allowance setup can be gasless
/// for the token holder.
contract FairShareToken is ERC20, ERC20Permit, Ownable {
    constructor(address initialOwner)
        ERC20("FairShare Token", "FST")
        ERC20Permit("FairShare Token")
        Ownable(initialOwner)
    {}

    function mint(address to, uint256 amount) external onlyOwner {
        _mint(to, amount);
    }
}
