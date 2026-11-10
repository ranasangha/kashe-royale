"""Stack-backed action history (with undo snapshots) and hand history.

The action stack records every event of a hand: blinds/deals, folds, checks,
calls, bets, raises, all-ins, burns, streets, showdowns and wins.  Player
actions store a deep snapshot of the game *before* the action, so a single
``pop()`` restores the exact previous state.  Auto events are pushed with
``snapshot=None``; undo pops those too and keeps going until it reaches a
record that can be restored (i.e. the player's last decision or the start of a
hand).

Undo is only exposed by the server when the table is in Demo/Practice mode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .stack import Stack, StackUnderflowError


@dataclass
class ActionRecord:
    seq: int
    kind: str
    label: str
    seat: Optional[int] = None
    snapshot: Any = None
    public: bool = True

    def summary(self) -> dict:
        """Log representation.  Never includes the (large) snapshot."""
        return {
            "seq": self.seq,
            "kind": self.kind,
            "label": self.label,
            "seat": self.seat,
        }


class ActionHistory:
    def __init__(self, max_records: int = 4000) -> None:
        self._records: Stack = Stack()
        self._seq = 0
        self._max_records = max_records

    def record(self, kind: str, label: str, snapshot: Any = None, seat: Optional[int] = None) -> ActionRecord:
        self._seq += 1
        record = ActionRecord(self._seq, kind, label, seat, snapshot)
        self._records.push(record)
        # Keep the visualizer/game memory bounded on very long sessions.
        if self._records.size() > self._max_records:
            # Rebuilding is rare and keeps the Stack ADT as the only storage.
            keep = self._records.to_list_bottom_first()[-self._max_records:]
            self._records.clear()
            for item in keep:
                self._records.push(item)
        return record

    def pop_undoable(self) -> Optional[ActionRecord]:
        """Pop records until one with a snapshot is found; return it."""
        while not self._records.is_empty():
            record = self._records.pop()
            if record.snapshot is not None:
                return record
        return None

    def size(self) -> int:
        return self._records.size()

    def is_empty(self) -> bool:
        return self._records.is_empty()

    def recent(self, limit: int = 20) -> list[dict]:
        return [record.summary() for record in self._records.to_list_top_first()[:limit]]

    def top(self) -> Optional[dict]:
        if self._records.is_empty():
            return None
        return self._records.peek().summary()

    def clear(self) -> None:
        self._records.clear()


@dataclass
class HandSummary:
    hand_no: int
    winners: list[dict] = field(default_factory=list)
    amount: int = 0
    reason: str = "showdown"
    hand_name: Optional[str] = None
    board: list[str] = field(default_factory=list)
    players: list[str] = field(default_factory=list)
    at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "hand_no": self.hand_no,
            "winners": self.winners,
            "amount": self.amount,
            "reason": self.reason,
            "hand_name": self.hand_name,
            "board": self.board,
            "players": self.players,
            "at": self.at,
        }


class HandHistory:
    """Completed hands on a Stack: newest hand is on top (last hand first)."""

    def __init__(self) -> None:
        self._hands: Stack = Stack()

    def push(self, summary: HandSummary) -> None:
        self._hands.push(summary)

    def peek(self) -> Optional[HandSummary]:
        return None if self._hands.is_empty() else self._hands.peek()

    def top_first(self, limit: int = 10) -> list[dict]:
        return [hand.to_dict() for hand in self._hands.to_list_top_first()[:limit]]

    def size(self) -> int:
        return self._hands.size()

    def clear(self) -> None:
        self._hands.clear()
