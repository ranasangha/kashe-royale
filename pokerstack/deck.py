"""A 52-card deck implemented on top of our hand-written Stack.

* ``cards`` is a Stack.  Shuffling produces a random order that is pushed onto
  the stack, so the *top* of the stack is the next card dealt.
* Dealing = ``pop()`` from the deck stack.
* Burning = ``pop()`` from the deck, then ``push()`` onto the burn Stack.
* ``peek_top()`` exists for demo mode only.  The server never sends the value
  of a hidden card to players in normal mode.

Shuffling uses ``random.SystemRandom`` (backed by the OS CSPRNG via secrets)
for a fair, unpredictable order.
"""

from __future__ import annotations

import copy
import random
from typing import Iterable, Optional

from .cards import Card, Suit
from .stack import Stack


class DeckEmptyError(Exception):
    """Raised when a card is requested from an empty deck."""


class Deck:
    def __init__(self, shuffle: bool = True, seed: Optional[int] = None) -> None:
        self.cards: Stack = Stack()
        self.burn: Stack = Stack()          # face-down burn cards
        self._rng = random.SystemRandom() if seed is None else random.Random(seed)
        if shuffle:
            self.reset()
        else:
            self._load_ordered()

    # ------------------------------------------------------------------ setup
    @staticmethod
    def full_deck() -> list[Card]:
        """The canonical 52 distinct cards."""
        return [Card(rank, suit) for suit in Suit for rank in range(2, 15)]

    def _load_ordered(self) -> None:
        self.cards.clear()
        self.burn.clear()
        for card in self.full_deck():
            self.cards.push(card)

    def reset(self) -> None:
        """Shuffle a fresh 52-card deck onto the stack.  O(52)."""
        self.cards.clear()
        self.burn.clear()
        order = self.full_deck()
        self._rng.shuffle(order)
        # Push so that order[-1] (the last shuffled card) ends up on top.
        for card in order:
            self.cards.push(card)

    def rig(self, deal_order: Iterable[Card]) -> None:
        """Test helper: make the next N deals follow ``deal_order`` exactly.

        ``deal_order`` is top-first.  The remaining cards are appended below.
        """
        wanted = list(deal_order)
        if len(set(wanted)) != len(wanted):
            raise ValueError("rigged deck contains duplicate cards")
        remaining = [c for c in Deck.full_deck() if c not in wanted]
        self.cards.clear()
        self.burn.clear()
        for card in reversed(wanted + remaining):
            self.cards.push(card)

    # -------------------------------------------------------------------- play
    def deal(self) -> Card:
        """Deal one card = pop the top of the deck stack.  O(1)."""
        if self.cards.is_empty():
            raise DeckEmptyError("The deck is empty; cannot deal another card.")
        return self.cards.pop()

    def burn_one(self) -> Card:
        """Burn one card: pop from deck, push face-down onto the burn stack."""
        card = self.deal()
        self.burn.push(card)
        return card

    # ------------------------------------------------------------------ checks
    @property
    def remaining(self) -> int:
        return self.cards.size()

    @property
    def burn_count(self) -> int:
        return self.burn.size()

    def peek_top(self) -> Card:
        """Look at the next card (demo/debug only).  Does not remove it."""
        return self.cards.peek()

    def all_dealt_and_burned(self) -> list[Card]:
        """Every card that has left the deck (for duplicate checks in tests)."""
        return self.cards.to_list_top_first() + self.burn.to_list_top_first()

    def __deepcopy__(self, memo: dict) -> "Deck":
        """Snapshots copy the cards and burn pile, never the OS entropy source."""
        new = Deck.__new__(Deck)
        new.cards = copy.deepcopy(self.cards, memo)
        new.burn = copy.deepcopy(self.burn, memo)
        if isinstance(self._rng, random.SystemRandom):
            new._rng = random.SystemRandom()
        else:
            new._rng = random.Random()
            new._rng.setstate(self._rng.getstate())
        return new

    def __repr__(self) -> str:
        return f"Deck(remaining={self.remaining}, burned={self.burn_count})"
