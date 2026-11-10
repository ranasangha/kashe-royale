"""Texas Hold'em hand evaluation: best five cards out of seven.

The evaluator checks all 21 possible five-card combinations of a player's two
hole cards plus the five community cards, scores each one, and keeps the best.
This is intentionally simple and easy to explain in a presentation (21 small
iterations per player, once per hand).

Hand strength is a tuple ``(category, tiebreak...)``.  Comparing tuples gives
correct poker ordering.  The exact five winning Card objects are returned so
the browser can highlight them.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from typing import Iterable, Sequence

from .cards import Card, RANK_LABELS, RANK_WORDS, Suit

# Category numbers: bigger is stronger.
HIGH_CARD = 0
ONE_PAIR = 1
TWO_PAIR = 2
THREE_OF_A_KIND = 3
STRAIGHT = 4
FLUSH = 5
FULL_HOUSE = 6
FOUR_OF_A_KIND = 7
STRAIGHT_FLUSH = 8

CATEGORY_NAMES = {
    HIGH_CARD: "High Card",
    ONE_PAIR: "One Pair",
    TWO_PAIR: "Two Pair",
    THREE_OF_A_KIND: "Three of a Kind",
    STRAIGHT: "Straight",
    FLUSH: "Flush",
    FULL_HOUSE: "Full House",
    FOUR_OF_A_KIND: "Four of a Kind",
    STRAIGHT_FLUSH: "Straight Flush",
}


@dataclass(frozen=True)
class HandValue:
    """The evaluated strength and the exact five cards that make it."""

    category: int
    tiebreak: tuple[int, ...]
    name: str
    cards: tuple[Card, ...]

    @property
    def key(self) -> tuple:
        return (self.category,) + self.tiebreak

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "category_name": CATEGORY_NAMES[self.category],
            "name": self.name,
            "cards": [card.to_dict() for card in self.cards],
            "key": list(self.key),
        }


def _straight_high(ranks: Iterable[int]) -> int | None:
    """Return the high card of a 5-card straight, or None.

    The wheel (A-2-3-4-5) is handled by treating the Ace as rank 1 when it
    appears; Q-K-A-2-3 is *not* a straight because there is no five-card run.
    """
    unique = sorted(set(ranks), reverse=True)
    if 14 in unique:
        unique.append(1)
    run = 1
    for index in range(1, len(unique)):
        if unique[index] == unique[index - 1] - 1:
            run += 1
            if run >= 5:
                return unique[index] + 4
        else:
            run = 1
    return None


def _straight_name(high: int) -> str:
    if high == 14:
        return "Straight, Ten to Ace"
    if high == 5:
        return "Straight, Five High (Wheel)"
    low = high - 4
    return f"Straight, {RANK_WORDS[low]} to {RANK_WORDS[high]}"


def evaluate_five(cards: Sequence[Card]) -> HandValue:
    """Score exactly five cards."""
    if len(cards) != 5:
        raise ValueError("evaluate_five requires exactly 5 cards")
    cards = tuple(cards)
    ranks = [card.rank for card in cards]
    counts = Counter(ranks)
    # (count, rank) descending: pairs/trips/quads first, then kickers.
    grouped = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    flush = all(card.suit == cards[0].suit for card in cards)
    straight_high = _straight_high(ranks)
    ordered_ranks = tuple(sorted(ranks, reverse=True))

    if flush and straight_high is not None:
        category = STRAIGHT_FLUSH
        tiebreak = (straight_high,)
        if straight_high == 14:
            name = "Royal Flush"
        else:
            name = "Straight Flush, " + RANK_WORDS[straight_high] + " High"
        return HandValue(category, tiebreak, name, cards)

    if grouped[0][1] == 4:
        quad = grouped[0][0]
        kicker = max(rank for rank in ranks if rank != quad)
        return HandValue(
            FOUR_OF_A_KIND, (quad, kicker),
            f"Four of a Kind, {RANK_WORDS[quad]}s", cards,
        )

    if grouped[0][1] == 3 and grouped[1][1] >= 2:
        trip = grouped[0][0]
        pair = grouped[1][0]
        return HandValue(
            FULL_HOUSE, (trip, pair),
            f"Full House, {RANK_WORDS[trip]}s over {RANK_WORDS[pair]}s", cards,
        )

    if flush:
        return HandValue(
            FLUSH, ordered_ranks,
            f"Flush, {RANK_WORDS[ordered_ranks[0]]} High", cards,
        )

    if straight_high is not None:
        return HandValue(STRAIGHT, (straight_high,), _straight_name(straight_high), cards)

    if grouped[0][1] == 3:
        trip = grouped[0][0]
        kickers = tuple(sorted((rank for rank in ranks if rank != trip), reverse=True))
        return HandValue(
            THREE_OF_A_KIND, (trip,) + kickers,
            f"Three of a Kind, {RANK_WORDS[trip]}s", cards,
        )

    pairs = sorted((rank for rank, count in counts.items() if count == 2), reverse=True)
    if len(pairs) == 2:
        high_pair, low_pair = pairs
        kicker = max(rank for rank in ranks if rank not in pairs)
        return HandValue(
            TWO_PAIR, (high_pair, low_pair, kicker),
            f"Two Pair, {RANK_WORDS[high_pair]}s and {RANK_WORDS[low_pair]}s", cards,
        )

    if len(pairs) == 1:
        pair = pairs[0]
        kickers = tuple(sorted((rank for rank in ranks if rank != pair), reverse=True))
        return HandValue(
            ONE_PAIR, (pair,) + kickers,
            f"Pair of {RANK_WORDS[pair]}s", cards,
        )

    return HandValue(
        HIGH_CARD, ordered_ranks,
        f"High Card, {RANK_WORDS[ordered_ranks[0]]}", cards,
    )


def evaluate(cards: Sequence[Card]) -> HandValue:
    """Return the best five-card hand from 5, 6 or 7 cards."""
    cards = tuple(cards)
    if len(cards) < 5:
        raise ValueError("At least 5 cards are required to evaluate a hand")
    best: HandValue | None = None
    for combo in combinations(cards, 5):
        value = evaluate_five(combo)
        if best is None or value.key > best.key:
            best = value
    assert best is not None
    return best


def best_five(cards: Sequence[Card]) -> tuple[Card, ...]:
    return evaluate(cards).cards


def compare(left: HandValue, right: HandValue) -> int:
    """1 if left wins, -1 if right wins, 0 for a tie (suits never matter)."""
    if left.key > right.key:
        return 1
    if left.key < right.key:
        return -1
    return 0
