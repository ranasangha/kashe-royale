"""Pots, side pots and odd chips.

Pot layers are built from each player's total contribution to the hand and
stored on a ``Stack``:

    bottom  [ main pot ] [ side pot 1 ] [ side pot 2 ]  top
                                                   ^ resolve top-down

At showdown the engine evaluates each layer separately for the players
eligible to win it.  Folded players' chips stay in the pot but those players
can never win a layer.

Odd-chip rule used consistently everywhere: when a pot does not divide evenly,
the extra single chips are awarded to the tied winners in clockwise order
starting with the first seat to the left of the dealer button.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .stack import Stack


@dataclass(frozen=True)
class PotLayer:
    amount: int
    eligible: tuple[int, ...]   # seat numbers that may win this layer
    label: str

    def to_dict(self) -> dict:
        return {
            "amount": self.amount,
            "eligible": list(self.eligible),
            "label": self.label,
        }


class PotStack:
    """A Stack of PotLayer objects (main pot at the bottom)."""

    def __init__(self) -> None:
        self._layers: Stack = Stack()

    def push_layer(self, layer: PotLayer) -> None:
        self._layers.push(layer)

    def clear(self) -> None:
        self._layers.clear()

    def top_layer(self) -> PotLayer:
        return self._layers.peek()

    def layers_top_first(self) -> list[PotLayer]:
        return self._layers.to_list_top_first()

    def layers_bottom_first(self) -> list[PotLayer]:
        return self._layers.to_list_bottom_first()

    def size(self) -> int:
        return self._layers.size()

    def total(self) -> int:
        return sum(layer.amount for layer in self._layers)

    def is_empty(self) -> bool:
        return self._layers.is_empty()

    def to_dict(self) -> dict:
        """Top-first for the visualizer: top of stack is resolved first."""
        return {
            "total": self.total(),
            "layers_top_first": [layer.to_dict() for layer in self.layers_top_first()],
        }


def build_pots(
    contributions: Mapping[int, int],
    folded: Iterable[int] = (),
) -> list[PotLayer]:
    """Build main + side pots, bottom-first, from seat -> total contribution.

    * only non-folded players are eligible to win;
    * folded chips still belong to the pots;
    * a layer is capped at each different all-in contribution level, so a
      player can only win the money they could match.
    """
    folded_set = set(folded)
    all_seats = [seat for seat, amount in contributions.items() if amount > 0]
    eligible = sorted(
        seat for seat, amount in contributions.items()
        if amount > 0 and seat not in folded_set
    )
    total = sum(contributions.get(seat, 0) for seat in all_seats)
    if total <= 0:
        return []

    # Each eligible player's total is a natural cap for a pot layer.
    levels = sorted({contributions[seat] for seat in eligible})
    layers: list[PotLayer] = []
    previous = 0
    for level in levels:
        amount = 0
        for seat in all_seats:
            amount += max(0, min(contributions[seat], level) - min(contributions[seat], previous))
        if amount > 0:
            winners_here = tuple(
                seat for seat in eligible if contributions[seat] >= level
            )
            label = "Main Pot" if not layers else f"Side Pot {len(layers)}"
            layers.append(PotLayer(amount, winners_here, label))
        previous = level

    # Money contributed by folded players above the highest eligible level is
    # dead money that belongs to the top pot.
    remaining = sum(max(0, amount - previous) for amount in contributions.values())
    if remaining > 0:
        if layers:
            last = layers[-1]
            layers[-1] = PotLayer(last.amount + remaining, last.eligible, last.label)
        else:
            # No one eligible contributed, but folded money exists: contested
            # by every remaining player.
            layers.append(PotLayer(remaining, tuple(eligible), "Main Pot"))

    return layers


def split_pot(amount: int, winners_in_order: Iterable[int]) -> dict[int, int]:
    """Split ``amount`` among winners, giving odd chips to the first seats.

    ``winners_in_order`` must already be sorted by the table's odd-chip rule
    (first seat clockwise from the dealer first).
    """
    winners = list(winners_in_order)
    if not winners:
        return {}
    share, remainder = divmod(int(amount), len(winners))
    result = {seat: share for seat in winners}
    for index in range(remainder):
        result[winners[index]] += 1
    return result
