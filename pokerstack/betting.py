"""No-Limit Texas Hold'em betting rules.

Kept free of game-state objects so the rules are easy to read and unit test.
The game engine calls :func:`validate_wager` with the current betting context.

Key rules implemented here:

* a bet must be at least the big blind (unless it is a short all-in);
* a raise must be at least as large as the previous full bet/raise;
* a short all-in raise is legal but does **not** reopen the betting for players
  who already acted (they may only call or fold);
* nobody may wager more chips than they have.
"""

from __future__ import annotations

from dataclasses import dataclass


class ActionError(Exception):
    """An illegal player action.  The message is shown to the player."""


@dataclass(frozen=True)
class Wager:
    """A validated bet/raise, expressed as a *raise-to* total for the street."""

    target: int        # total chips this player will have in for this street
    delta: int         # extra chips taken from their stack
    full_raise: bool   # does this count as a full raise (reopens betting)?
    is_all_in: bool


def validate_wager(
    *,
    current_bet: int,
    min_raise: int,
    big_blind: int,
    player_bet: int,
    chips: int,
    amount: int,
    short_call_only: bool = False,
) -> Wager:
    """Validate a bet/raise target and return a :class:`Wager`.

    ``amount`` is the total street bet the player wants to reach ("raise to
    X"), not the extra amount on top.  This is how the UI slider works.
    """
    if chips <= 0:
        raise ActionError("You have no chips left to bet.")
    to_call = max(0, current_bet - player_bet)
    try:
        target = int(amount)
    except (TypeError, ValueError):
        raise ActionError("Bet amount must be a whole number of chips.")

    if target <= player_bet:
        raise ActionError("That amount does not increase your bet.")
    max_target = player_bet + chips
    if target > max_target:
        raise ActionError(
            f"You only have {chips} chips available; your maximum bet is {max_target}."
        )
    is_all_in = target == max_target

    if to_call > 0 and target <= current_bet:
        raise ActionError("That is a call, not a raise. Use the Call button.")
    if current_bet == 0 and target <= 0:
        raise ActionError("Bet must be greater than zero.")
    if short_call_only:
        raise ActionError(
            "A short all-in did not reopen the betting. You may only call or fold."
        )

    if current_bet == 0:
        # Opening bet for this street.
        if target < big_blind and not is_all_in:
            raise ActionError(
                f"The minimum bet is {big_blind}. (A shorter all-in is still allowed.)"
            )
        full_raise = target >= big_blind
    else:
        minimum_target = current_bet + min_raise
        if target < minimum_target and not is_all_in:
            raise ActionError(
                f"The minimum raise is to {minimum_target} "
                f"(call {to_call} + raise {min_raise})."
            )
        full_raise = target >= minimum_target

    return Wager(
        target=target,
        delta=target - player_bet,
        full_raise=full_raise,
        is_all_in=is_all_in,
    )


def minimum_bet_target(*, current_bet: int, min_raise: int, big_blind: int, player_bet: int) -> int:
    """The smallest legal *full* bet/raise-to target for display in the UI."""
    if current_bet == 0:
        return big_blind
    return current_bet + min_raise


def max_bet_target(player_bet: int, chips: int) -> int:
    return player_bet + chips
