"""Playing cards: immutable Card values, suits and ranks.

Ranks are integers 2..14 (11=J, 12=Q, 13=K, 14=A) so comparing poker hands is
simple arithmetic.  Suits are an Enum with a stable single-letter code, a
Unicode symbol and a colour for the UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class Suit(Enum):
    CLUBS = ("c", "\u2663", "black")
    DIAMONDS = ("d", "\u2666", "red")
    HEARTS = ("h", "\u2665", "red")
    SPADES = ("s", "\u2660", "black")

    @property
    def code(self) -> str:
        return self.value[0]

    @property
    def symbol(self) -> str:
        return self.value[1]

    @property
    def colour(self) -> str:
        return self.value[2]

    @classmethod
    def from_code(cls, code: str) -> "Suit":
        code = code.lower()
        for suit in cls:
            if suit.code == code:
                return suit
        raise ValueError(f"Unknown suit code: {code!r}")


RANK_LABELS = {
    2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9",
    10: "10", 11: "J", 12: "Q", 13: "K", 14: "A",
}
RANK_WORDS = {
    2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven",
    8: "Eight", 9: "Nine", 10: "Ten", 11: "Jack", 12: "Queen", 13: "King",
    14: "Ace",
}
_RANK_CODES = {label: rank for rank, label in RANK_LABELS.items()}
_RANK_CODES["T"] = 10


@dataclass(frozen=True, order=False)
class Card:
    """A single playing card.  ``rank`` is 2..14, ``suit`` is a Suit."""

    rank: int
    suit: Suit

    def __post_init__(self) -> None:
        if not isinstance(self.rank, int) or not 2 <= self.rank <= 14:
            raise ValueError(f"Invalid card rank: {self.rank!r}")
        if not isinstance(self.suit, Suit):
            raise ValueError(f"Invalid card suit: {self.suit!r}")

    @property
    def rank_label(self) -> str:
        return RANK_LABELS[self.rank]

    @property
    def rank_word(self) -> str:
        return RANK_WORDS[self.rank]

    @property
    def code(self) -> str:
        """Machine code such as ``AS``, ``TD``, ``7H``."""
        return f"{self.rank_label}{self.suit.code.upper()}"

    @property
    def label(self) -> str:
        """Human label such as ``A\u2660``."""
        return f"{self.rank_label}{self.suit.symbol}"

    @classmethod
    def from_code(cls, code: str) -> "Card":
        """Parse ``AS``, ``10h``, ``Ts``, ``7D`` (case-insensitive)."""
        if not isinstance(code, str) or len(code) < 2:
            raise ValueError(f"Invalid card code: {code!r}")
        code = code.strip()
        suit = Suit.from_code(code[-1])
        rank_part = code[:-1].upper()
        if rank_part not in _RANK_CODES:
            raise ValueError(f"Invalid card rank in {code!r}")
        return cls(_RANK_CODES[rank_part], suit)

    def to_dict(self) -> dict:
        """JSON-friendly representation used by the web API."""
        return {
            "rank": self.rank,
            "rank_label": self.rank_label,
            "suit": self.suit.code,
            "symbol": self.suit.symbol,
            "colour": self.suit.colour,
            "label": self.label,
            "code": self.code,
        }

    def __str__(self) -> str:
        return self.label


def parse_cards(text: str) -> list[Card]:
    """Parse a whitespace/comma separated list, e.g. ``"AS KH 10D"``."""
    tokens = text.replace(",", " ").split()
    return [Card.from_code(token) for token in tokens]


def cards_to_dicts(cards: Iterable[Card]) -> list[dict]:
    return [card.to_dict() for card in cards]
