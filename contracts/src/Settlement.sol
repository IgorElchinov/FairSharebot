// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";

/// @notice The only contract allowed to move tokens between FairSharebot
/// users. Every wallet grants this contract a standing allowance once (via
/// FairShareToken's permit); from then on the bot's relayer is the sole
/// caller able to pull funds, batched per payment or per /closetrip
/// settlement round.
///
/// settleBatch is intentionally all-or-nothing: a single failing transfer
/// reverts the whole batch rather than partially applying it. "Best effort
/// across a trip" is achieved by the caller submitting many small batches
/// (one per payment, one per residual transfer at close), not by partial
/// execution inside this contract.
contract Settlement is Ownable, Pausable {
    struct Transfer {
        address from;
        address to;
        uint256 amount;
    }

    IERC20 public immutable token;
    address public relayer;

    event RelayerUpdated(address indexed newRelayer);
    event TransferSettled(address indexed from, address indexed to, uint256 amount);

    error NotRelayer();

    modifier onlyRelayer() {
        if (msg.sender != relayer) revert NotRelayer();
        _;
    }

    constructor(address initialOwner, IERC20 token_, address initialRelayer) Ownable(initialOwner) {
        token = token_;
        relayer = initialRelayer;
    }

    function setRelayer(address newRelayer) external onlyOwner {
        relayer = newRelayer;
        emit RelayerUpdated(newRelayer);
    }

    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }

    function settleBatch(Transfer[] calldata transfers) external onlyRelayer whenNotPaused {
        uint256 len = transfers.length;
        for (uint256 i = 0; i < len; i++) {
            Transfer calldata t = transfers[i];
            require(token.transferFrom(t.from, t.to, t.amount), "transferFrom failed");
            emit TransferSettled(t.from, t.to, t.amount);
        }
    }
}
