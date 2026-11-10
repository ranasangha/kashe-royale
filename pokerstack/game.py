"""The authoritative No-Limit Texas Hold'em game engine.

Everything about a hand lives here: seats, dealer button, blinds, dealing,
betting, side pots, showdown, timers, undo, and per-player state filtering.
The browser never mutates state; it only receives a filtered view and sends
validated actions.

Stack usage in this module
--------------------------
* ``Deck`` (deck.py) is a Stack: deal = pop, burn = push.
* Every event is pushed onto the action-history Stack; undo = pop + restore.
* Side-pot layers are pushed onto a ``PotStack`` and resolved top-down.
* Completed hands are pushed onto the hand-history Stack.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Optional

from .betting import ActionError, minimum_bet_target, validate_wager
from .cards import Card
from .deck import Deck
from .evaluator import HandValue, evaluate
from .history import ActionHistory, HandHistory, HandSummary
from .pots import PotLayer, PotStack, build_pots, split_pot

ACTIVE_PHASES = ("preflop", "flop", "turn", "river")
STREETS = ("preflop", "flop", "turn", "river")
PHASES = ("waiting", "preflop", "flop", "turn", "river", "hand_over")


class GameError(Exception):
    """An invalid request to the game engine."""


def _clamp_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


@dataclass
class TableSettings:
    name: str = "Royal Table"
    min_players: int = 2
    max_players: int = 6
    starting_chips: int = 1000
    small_blind: int = 5
    big_blind: int = 10
    turn_seconds: int = 30
    late_join: bool = True
    spectators: bool = True
    private: bool = True
    demo_mode: bool = False

    def __post_init__(self) -> None:
        self.name = (self.name or "Royal Table").strip()[:40] or "Royal Table"
        self.max_players = _clamp_int(self.max_players, 6, 2, 10)
        self.min_players = _clamp_int(self.min_players, 2, 2, self.max_players)
        self.starting_chips = _clamp_int(self.starting_chips, 1000, 10, 10_000_000)
        self.small_blind = _clamp_int(self.small_blind, 5, 1, 1_000_000)
        self.big_blind = _clamp_int(self.big_blind, 10, 2, 2_000_000)
        if self.big_blind < self.small_blind:
            self.big_blind = self.small_blind
        if self.starting_chips < self.big_blind:
            self.starting_chips = self.big_blind
        self.turn_seconds = _clamp_int(self.turn_seconds, 30, 0, 300)
        self.late_join = bool(self.late_join)
        self.spectators = bool(self.spectators)
        self.private = bool(self.private)
        self.demo_mode = bool(self.demo_mode)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "min_players": self.min_players,
            "max_players": self.max_players,
            "starting_chips": self.starting_chips,
            "small_blind": self.small_blind,
            "big_blind": self.big_blind,
            "turn_seconds": self.turn_seconds,
            "late_join": self.late_join,
            "spectators": self.spectators,
            "private": self.private,
            "demo_mode": self.demo_mode,
        }

    @classmethod
    def from_dict(cls, data: dict, demo_mode: bool = False) -> "TableSettings":
        return cls(
            name=data.get("name") or data.get("table_name") or "Royal Table",
            min_players=data.get("min_players", 2),
            max_players=data.get("max_players", 6),
            starting_chips=data.get("starting_chips", 1000),
            small_blind=data.get("small_blind", 5),
            big_blind=data.get("big_blind", 10),
            turn_seconds=data.get("turn_seconds", 30),
            late_join=data.get("late_join", True),
            spectators=data.get("spectators", True),
            private=data.get("private", True),
            demo_mode=demo_mode or bool(data.get("demo_mode", False)),
        )


@dataclass
class Player:
    id: str
    name: str
    seat: int
    chips: int
    connected: bool = True
    sitting_out: bool = False
    waiting: bool = False          # joined while a hand was running
    leaving: bool = False
    is_host: bool = False

    # Per-hand fields
    cards: list[Card] = field(default_factory=list)
    folded: bool = False
    all_in: bool = False
    in_hand: bool = False
    bet: int = 0                   # chips committed this street
    contributed: int = 0           # chips committed this whole hand
    acted: bool = False
    short_call_only: bool = False
    last_action: str = ""
    is_winner: bool = False
    won: int = 0

    # Connection helper
    disconnected_at: float = 0.0

    def reset_for_hand(self) -> None:
        self.cards = []
        self.folded = False
        self.all_in = False
        self.in_hand = False
        self.bet = 0
        self.contributed = 0
        self.acted = False
        self.short_call_only = False
        self.last_action = ""
        self.is_winner = False
        self.won = 0


class Game:
    def __init__(self, settings: TableSettings, host_id: str, practice: bool = False) -> None:
        self.settings = settings
        self.host_id = host_id
        self.practice = practice
        self.seats: list[Optional[Player]] = [None] * settings.max_players
        self.phase = "waiting"
        self.street = "preflop"
        self.hand_no = 0
        self.dealer_seat: Optional[int] = None
        self.sb_seat: Optional[int] = None
        self.bb_seat: Optional[int] = None
        self.actor_seat: Optional[int] = None
        self.turn_started: Optional[float] = None
        self.turn_deadline: Optional[float] = None
        self.current_bet = 0
        self.min_raise = settings.big_blind
        self.community: list[Card] = []
        self.deck = Deck(shuffle=False)
        self.pot_stack = PotStack()
        self.result: Optional[dict] = None
        self.message = "Waiting for players."
        self.chip_total = 0
        self.version = 0
        self.action_stack = ActionHistory()
        self.hand_history = HandHistory()
        self.viz_events: list[dict] = []
        self._event_seq = 0
        self.removed_ids: list[str] = []
        self._last_activity = time.time()
        self._auto_actions_in_tick = 0

    # ------------------------------------------------------------------ helpers
    def _bump(self) -> None:
        self.version += 1
        self._last_activity = time.time()

    def _seated(self) -> list[Player]:
        return [p for p in self.seats if p is not None]

    def _seated_sorted(self) -> list[Player]:
        return sorted(self._seated(), key=lambda p: p.seat)

    def _in_hand(self) -> list[Player]:
        return [p for p in self._seated() if p.in_hand]

    def _active(self) -> list[Player]:
        return [p for p in self._in_hand() if not p.folded]

    def _actors(self) -> list[Player]:
        return [p for p in self._active() if not p.all_in and p.chips > 0]

    def _player(self, player_id: str) -> Player:
        for player in self._seated():
            if player.id == player_id:
                return player
        raise GameError("You are not seated at this table.")

    def player_at(self, seat: int) -> Optional[Player]:
        if 0 <= seat < len(self.seats):
            return self.seats[seat]
        return None

    def _next_seat(self, seat: int) -> int:
        return (seat + 1) % self.settings.max_players

    def _seats_after(self, seat: int) -> Iterable[int]:
        for step in range(1, self.settings.max_players + 1):
            yield (seat + step) % self.settings.max_players

    def _next_player_after(self, seat: int, players: Iterable[Player]) -> Optional[Player]:
        wanted = {p.seat for p in players}
        for candidate in self._seats_after(seat):
            if candidate in wanted:
                return self.player_at(candidate)
        return None

    def _clockwise_key(self, seat: int) -> int:
        """Sort key: first seat clockwise from the dealer gets 0."""
        if self.dealer_seat is None:
            return seat
        return (seat - self.dealer_seat - 1) % max(1, self.settings.max_players)

    def _revealed_seats(self) -> set[int]:
        if self.phase == "hand_over" and self.result and self.result.get("reason") == "showdown":
            return {entry["seat"] for entry in self.result.get("revealed", [])}
        return set()

    # ---------------------------------------------------------------- viz log
    def _viz(self, stack_name: str, operation: str, label: str,
             detail: Optional[str] = None, hidden: bool = False) -> None:
        self._event_seq += 1
        self.viz_events.append({
            "id": self._event_seq,
            "stack": stack_name,
            "op": operation,
            "label": label,
            "detail": detail,
            "hidden": hidden,
        })
        if len(self.viz_events) > 120:
            del self.viz_events[:-120]

    def _record(self, kind: str, label: str, snapshot: Any = None,
                seat: Optional[int] = None) -> None:
        self.action_stack.record(kind, label, snapshot, seat)
        self._viz("action", "push", label, kind)

    def _auto_record(self, kind: str, label: str) -> None:
        self.action_stack.record(kind, label, None, None)
        self._viz("action", "push", label, kind)

    # --------------------------------------------------------------- snapshots
    _SNAP_ATTRS = (
        "settings", "host_id", "phase", "street", "hand_no", "dealer_seat",
        "sb_seat", "bb_seat", "actor_seat", "turn_started", "turn_deadline",
        "current_bet", "min_raise", "community", "deck", "pot_stack", "result",
        "message", "chip_total", "hand_history",
    )

    def _snapshot(self) -> dict:
        snap: dict[str, Any] = {}
        for attr in self._SNAP_ATTRS:
            snap[attr] = copy.deepcopy(getattr(self, attr))
        snap["seats"] = copy.deepcopy(self.seats)
        return snap

    def _restore(self, snap: dict) -> None:
        for attr, value in snap.items():
            if attr == "seats":
                self.seats = copy.deepcopy(value)
            else:
                setattr(self, attr, copy.deepcopy(value))
        if self.phase in ACTIVE_PHASES and self.actor_seat is not None:
            self.turn_started = time.time()
            self.turn_deadline = (
                self.turn_started + self.settings.turn_seconds
                if self.settings.turn_seconds > 0 else None
            )
        else:
            self.turn_started = None
            self.turn_deadline = None
        self.version += 1
        self._last_activity = time.time()

    # ------------------------------------------------------------------- seats
    def add_player(self, player_id: str, name: str, chips: Optional[int] = None) -> Player:
        for p in self._seated():
            if p.id == player_id:
                return p
        if self.phase in ACTIVE_PHASES and not self.settings.late_join:
            raise GameError("Late joining is disabled at this table.")
        free = None
        for index, seat in enumerate(self.seats):
            if seat is None:
                free = index
                break
        if free is None:
            raise GameError("This table is full.")
        clean_name = (name or "Player").strip()[:18] or "Player"
        buy_in = min(max(int(chips if chips is not None else self.settings.starting_chips), 1),
                     10_000_000)
        player = Player(
            id=player_id, name=clean_name, seat=free, chips=buy_in,
            waiting=self.phase in ACTIVE_PHASES,
            is_host=(player_id == self.host_id),
        )
        self.seats[free] = player
        self.chip_total += buy_in
        self._bump()
        return player

    def add_player_at(self, player_id: str, name: str, seat: int,
                      chips: Optional[int] = None) -> Player:
        if not 0 <= seat < self.settings.max_players:
            raise GameError("That seat does not exist.")
        if self.seats[seat] is not None:
            raise GameError("That seat is already taken.")
        for p in self._seated():
            if p.id == player_id:
                return p
        clean_name = (name or "Player").strip()[:18] or "Player"
        buy_in = max(int(chips if chips is not None else self.settings.starting_chips), 1)
        player = Player(id=player_id, name=clean_name, seat=seat, chips=buy_in,
                        waiting=self.phase in ACTIVE_PHASES,
                        is_host=(player_id == self.host_id))
        self.seats[seat] = player
        self.chip_total += buy_in
        self._bump()
        return player

    def set_host(self, player_id: str) -> None:
        old = self.host_id
        self.host_id = player_id
        for p in self._seated():
            p.is_host = p.id == player_id
        if old != player_id:
            self._bump()

    def _promote_host(self, previous_seat: int) -> None:
        candidates = [p for p in self._seated_sorted() if not p.leaving]
        if not candidates:
            self.set_host("")
            return
        # Prefer the next seat clockwise from the departing host.
        wanted = {p.seat for p in candidates}
        for seat in self._seats_after(previous_seat):
            if seat in wanted:
                self.set_host(self.seats[seat].id)  # type: ignore[union-attr]
                return
        self.set_host(candidates[0].id)

    def _finalize_leavers(self) -> None:
        if self.phase in ACTIVE_PHASES:
            return
        for player in list(self._seated()):
            if not player.leaving:
                continue
            seat = player.seat
            was_host = player.id == self.host_id
            self.chip_total -= player.chips
            self.seats[seat] = None
            self.removed_ids.append(player.id)
            self.message = f"{player.name} left the table."
            self._viz("action", "pop", f"{player.name} left the table")
            if was_host:
                self._promote_host(seat)
        self._bump()

    def pop_removed_ids(self) -> list[str]:
        removed = self.removed_ids
        self.removed_ids = []
        return removed

    # ------------------------------------------------------------------ start
    def start_game(self, requester_id: str) -> bool:
        if not self.practice and requester_id != self.host_id:
            raise GameError("Only the host can start the game.")
        if self.phase in ACTIVE_PHASES:
            raise GameError("A hand is already in progress.")
        return self.start_hand()

    def next_hand(self, requester_id: str) -> bool:
        if self.phase in ACTIVE_PHASES:
            raise GameError("Finish the current hand first.")
        if not self.practice and requester_id != self.host_id:
            if not any(p.id == requester_id for p in self._seated()):
                raise GameError("Only a seated player can start the next hand.")
        return self.start_hand()

    def _eligible_players(self, mark: bool = True) -> list[Player]:
        eligible = []
        for p in self._seated_sorted():
            if p.leaving:
                continue
            if p.sitting_out:
                continue
            if p.chips < self.settings.big_blind:
                if mark:
                    p.sitting_out = True
                    if p.chips > 0:
                        self.message = f"{p.name} sits out with less than a big blind (rebuy available)."
                continue
            eligible.append(p)
        return eligible

    def start_hand(self, deck_order: Optional[list[Card]] = None) -> bool:
        if self.phase in ACTIVE_PHASES:
            raise GameError("A hand is already in progress.")
        self._finalize_leavers()

        eligible = self._eligible_players()
        needed = max(2, self.settings.min_players)
        if len(eligible) < needed:
            self.phase = "waiting"
            self.actor_seat = None
            self.turn_deadline = None
            self.result = None
            self.message = f"Waiting for players ({len(eligible)}/{needed} seated)."
            self._bump()
            return False

        snap = self._snapshot()
        self.hand_no += 1
        self.phase = "preflop"
        self.street = "preflop"
        self.result = None
        self.community = []
        self.pot_stack = PotStack()
        self.current_bet = self.settings.big_blind
        self.min_raise = self.settings.big_blind
        self.actor_seat = None
        self.turn_deadline = None

        for player in self._seated():
            player.reset_for_hand()
            player.in_hand = player in eligible
            player.waiting = player not in eligible and not player.leaving

        # Dealer button: first hand at the host seat (or first seat), then move
        # clockwise to the next eligible player.
        eligible_seats = {p.seat for p in eligible}
        if self.dealer_seat is None or self.dealer_seat not in eligible_seats:
            host_seat = None
            for p in eligible:
                if p.id == self.host_id:
                    host_seat = p.seat
            if host_seat is not None:
                self.dealer_seat = host_seat
            else:
                self.dealer_seat = eligible[0].seat
        else:
            self.dealer_seat = next(
                seat for seat in self._seats_after(self.dealer_seat) if seat in eligible_seats
            )

        dealer = self.seats[self.dealer_seat]
        assert dealer is not None
        if len(eligible) == 2:
            sb_player = dealer
            bb_player = next(p for p in eligible if p.seat != dealer.seat)
        else:
            sb_player = next(
                self.player_at(seat) for seat in self._seats_after(dealer.seat)
                if seat in eligible_seats
            )
            assert sb_player is not None
            sb_seats = {p.seat for p in eligible}
            bb_player = next(
                self.player_at(seat) for seat in self._seats_after(sb_player.seat)
                if seat in sb_seats
            )
            assert bb_player is not None
        self.sb_seat = sb_player.seat
        self.bb_seat = bb_player.seat

        # Shuffle a fresh deck and push all 52 cards onto the deck Stack.
        self.deck = Deck()
        if deck_order:
            self.deck.rig(deck_order)
        self._viz("deck", "reset", "52 cards shuffled & pushed", f"size {self.deck.remaining}")

        # Blinds
        sb_amount = min(self.settings.small_blind, sb_player.chips)
        bb_amount = min(self.settings.big_blind, bb_player.chips)
        for player, amount, label in (
            (sb_player, sb_amount, "small blind"),
            (bb_player, bb_amount, "big blind"),
        ):
            player.chips -= amount
            player.bet = amount
            player.contributed = amount
            player.last_action = f"{label} {amount}"
            if player.chips == 0:
                player.all_in = True

        # Deal two private cards, one at a time, clockwise from the dealer.
        for _round in range(2):
            for seat in self._seats_after(dealer.seat):
                player = self.seats[seat]
                if player is None or not player.in_hand:
                    continue
                card = self.deck.deal()
                player.cards.append(card)
                self._viz("deck", "pop", "deal hole card",
                          card.label if (self.practice or self.settings.demo_mode) else None,
                          hidden=not (self.practice or self.settings.demo_mode))

        # Snapshot the whole setup so demo undo can rewind the deal as a unit.
        self._record(
            "hand_start",
            f"Hand #{self.hand_no}: blinds posted, hole cards dealt",
            snapshot=snap,
        )
        self._auto_record(
            "blind",
            f"Blinds: {sb_player.name} {sb_amount} / {bb_player.name} {bb_amount}",
        )
        self._auto_record("deal", "Hole cards dealt (2 each)")

        pending = self._pending_actors()
        if not pending:
            self._run_out_board()
        else:
            if len(eligible) == 2:
                first = dealer if dealer in pending else pending[0]
            else:
                first = self._next_player_after(self.bb_seat, pending) or pending[0]
            self._set_actor(first.seat)

        if self.phase in ACTIVE_PHASES and self.actor_seat is not None:
            actor = self.player_at(self.actor_seat)
            self.message = (
                f"Hand #{self.hand_no}. {actor.name if actor else 'Player'} to act."
            )
        self._bump()
        return True

    # ----------------------------------------------------------------- betting
    def _pending_actors(self) -> list[Player]:
        """Players who still owe a response this street."""
        actors = self._actors()
        if len(actors) <= 1:
            # With nobody left to bet against, only an outstanding call matters.
            return [p for p in actors if p.bet < self.current_bet]
        return [p for p in actors if (not p.acted) or p.bet < self.current_bet]

    def _set_actor(self, seat: Optional[int]) -> None:
        self.actor_seat = seat
        if seat is None or self.phase not in ACTIVE_PHASES:
            self.turn_started = None
            self.turn_deadline = None
            return
        self.turn_started = time.time()
        if self.settings.turn_seconds > 0:
            self.turn_deadline = self.turn_started + self.settings.turn_seconds
        else:
            self.turn_deadline = None

    def _finish_betting_round(self) -> None:
        self._end_street()

    def _advance_after_action(self, acted_seat: int) -> None:
        if self.phase not in ACTIVE_PHASES:
            return
        active = self._active()
        if len(active) <= 1:
            if active:
                self._finish_fold_win(active[0])
            return
        pending = self._pending_actors()
        if not pending:
            self._finish_betting_round()
            return
        nxt = self._next_player_after(acted_seat, pending)
        if nxt is None:
            nxt = pending[0]
        self._set_actor(nxt.seat)

    def legal_actions(self, player: Player) -> dict:
        """Everything the UI needs to enable/disable buttons, with reasons."""
        is_turn = self.phase in ACTIVE_PHASES and self.actor_seat == player.seat
        to_call = max(0, self.current_bet - player.bet)
        max_target = player.bet + player.chips
        min_target = (
            self.current_bet + self.min_raise
            if self.current_bet > 0
            else self.settings.big_blind
        )
        others_can_act = [
            p for p in self._actors() if p.seat != player.seat
        ]
        wager_reason = None
        wager_allowed = True
        if not is_turn:
            wager_allowed = False
            wager_reason = "It is not your turn."
        elif player.chips <= 0:
            wager_allowed = False
            wager_reason = "You have no chips left."
        elif player.short_call_only:
            wager_allowed = False
            wager_reason = "A short all-in did not reopen the betting; you may only call or fold."
        elif not others_can_act:
            wager_allowed = False
            wager_reason = "All other players are all-in or folded."
        elif max_target < min_target:
            wager_allowed = False
            wager_reason = (
                f"You need at least {min_target} to make a full raise; "
                "your only option is All-in."
            )

        call_allowed = is_turn and to_call > 0
        call_amount = min(to_call, player.chips) if call_allowed else 0
        check_allowed = is_turn and to_call == 0
        all_in_allowed = is_turn and player.chips > 0
        wager_min_allowed = max(min_target, player.bet + 1)
        return {
            "is_turn": is_turn,
            "to_call": to_call,
            "current_bet": self.current_bet,
            "min_raise": self.min_raise,
            "big_blind": self.settings.big_blind,
            "wager_label": "Bet" if self.current_bet == 0 else "Raise",
            "fold": {"allowed": is_turn, "reason": None if is_turn else "It is not your turn."},
            "check": {
                "allowed": check_allowed,
                "reason": None if check_allowed
                else ("It is not your turn." if not is_turn else f"Call {to_call} instead — a bet is outstanding."),
            },
            "call": {
                "allowed": call_allowed,
                "amount": call_amount,
                "all_in": bool(call_allowed and call_amount >= player.chips),
                "reason": None if call_allowed
                else ("It is not your turn." if not is_turn else "Nothing to call — you can check."),
            },
            "wager": {
                "allowed": wager_allowed,
                "min": wager_min_allowed,
                "max": max_target,
                "reason": wager_reason,
            },
            "all_in": {
                "allowed": all_in_allowed,
                "amount": max_target,
                "reason": None if all_in_allowed else "No chips available.",
            },
            "chips": player.chips,
            "bet": player.bet,
        }

    def act(self, player_id: str, action: str, amount: Optional[int] = None,
            seat: Optional[int] = None, _auto: bool = False) -> dict:
        """Validate and apply a player action.  Raises ActionError if illegal."""
        if self.phase not in ACTIVE_PHASES:
            raise GameError("There is no hand in progress.")
        if self.actor_seat is None:
            raise GameError("No player is currently to act.")
        target_player: Optional[Player]
        if self.practice and seat is not None:
            target_player = self.player_at(int(seat))
        else:
            target_player = next((p for p in self._seated() if p.id == player_id), None)
        if target_player is None:
            raise GameError("You are not seated at this table.")
        if target_player.seat != self.actor_seat:
            raise ActionError("It is not your turn.")

        action = (action or "").lower().replace(" ", "_").replace("-", "_")
        if action in ("all_in", "allin"):
            action = "allin"
        legal = self.legal_actions(target_player)
        to_call = legal["to_call"]
        snap = self._snapshot()
        label = ""
        player = target_player

        if action == "fold":
            player.folded = True
            player.acted = True
            player.last_action = "Fold"
            label = f"{player.name} folds"
        elif action == "check":
            if to_call > 0:
                raise ActionError(f"Cannot check: you must call {to_call} or fold.")
            player.acted = True
            player.last_action = "Check"
            label = f"{player.name} checks"
        elif action == "call":
            if to_call <= 0:
                raise ActionError("Nothing to call — you can check instead.")
            paid = min(to_call, player.chips)
            player.chips -= paid
            player.bet += paid
            player.contributed += paid
            player.acted = True
            player.short_call_only = False
            if player.chips == 0:
                player.all_in = True
            player.last_action = f"Call {paid}" + (" (all-in)" if player.all_in else "")
            label = f"{player.name} calls {paid}" + (" (all-in)" if player.all_in else "")
        elif action in ("bet", "raise"):
            if amount is None:
                raise ActionError("Enter an amount for your bet or raise.")
            wager = validate_wager(
                current_bet=self.current_bet,
                min_raise=self.min_raise,
                big_blind=self.settings.big_blind,
                player_bet=player.bet,
                chips=player.chips,
                amount=int(amount),
                short_call_only=player.short_call_only,
            )
            previous_bet = self.current_bet
            player.chips -= wager.delta
            player.bet += wager.delta
            player.contributed += wager.delta
            if wager.target > self.current_bet:
                self.current_bet = wager.target
                if wager.full_raise:
                    self.min_raise = max(
                        self.settings.big_blind, wager.target - previous_bet
                    )
                    for other in self._actors():
                        if other.seat != player.seat:
                            other.acted = False
                            other.short_call_only = False
                else:
                    # Short all-in: players who already acted may call/fold only.
                    for other in self._actors():
                        if other.seat == player.seat:
                            continue
                        if other.bet < self.current_bet:
                            if other.acted:
                                other.short_call_only = True
                            other.acted = False
            if player.chips == 0:
                player.all_in = True
            player.acted = True
            player.short_call_only = False
            verb = "bets" if previous_bet == 0 else "raises to"
            shown = wager.target if previous_bet > 0 else wager.delta
            player.last_action = (
                f"{'Bet' if previous_bet == 0 else 'Raise'} {shown}"
                + (" (all-in)" if player.all_in else "")
            )
            label = f"{player.name} {verb} {shown}" + (" (all-in)" if player.all_in else "")
        elif action == "allin":
            if player.chips <= 0:
                raise ActionError("You have no chips left.")
            target = player.bet + player.chips
            if target <= self.current_bet:
                # All-in call (possibly short).
                paid = player.chips
                player.chips = 0
                player.bet += paid
                player.contributed += paid
                player.all_in = True
                player.acted = True
                player.short_call_only = False
                player.last_action = f"All-in call {paid}"
                label = f"{player.name} calls all-in for {paid}"
            else:
                wager = validate_wager(
                    current_bet=self.current_bet,
                    min_raise=self.min_raise,
                    big_blind=self.settings.big_blind,
                    player_bet=player.bet,
                    chips=player.chips,
                    amount=target,
                    short_call_only=player.short_call_only,
                )
                previous_bet = self.current_bet
                player.chips = 0
                player.bet = target
                player.contributed += wager.delta
                player.all_in = True
                self.current_bet = target
                if wager.full_raise:
                    self.min_raise = max(self.settings.big_blind, target - previous_bet)
                    for other in self._actors():
                        if other.seat != player.seat:
                            other.acted = False
                            other.short_call_only = False
                else:
                    for other in self._actors():
                        if other.seat == player.seat:
                            continue
                        if other.bet < self.current_bet:
                            if other.acted:
                                other.short_call_only = True
                            other.acted = False
                player.acted = True
                player.short_call_only = False
                player.last_action = f"All-in {target}"
                label = f"{player.name} is all-in for {target}"
        else:
            raise ActionError("Unknown action.")

        self._record(
            action if action not in ("check", "call", "fold") else action,
            label + (" (timeout)" if _auto else ""),
            snapshot=snap,
            seat=player.seat,
        )
        self.message = label + (" — auto action" if _auto else "")
        self._advance_after_action(player.seat)
        self._bump()
        return {"label": label}

    # -------------------------------------------------------------- streets
    def _refund_uncalled(self) -> int:
        """Return an unmatched street bet to whoever made it.  Idempotent."""
        players = [p for p in self._in_hand() if p.bet > 0]
        if len(players) < 2:
            return 0
        ordered = sorted(players, key=lambda p: p.bet, reverse=True)
        top, second = ordered[0], ordered[1]
        if top.bet <= second.bet:
            return 0
        extra = top.bet - second.bet
        top.chips += extra
        top.bet -= extra
        top.contributed -= extra
        self.current_bet = max(p.bet for p in self._in_hand())
        self._auto_record(
            "refund",
            f"Uncalled {extra} returned to {top.name}",
        )
        self._viz("action", "push", f"Uncalled bet returned: {extra}", top.name)
        return extra

    def _deal_next_street(self) -> None:
        if self.street == "preflop":
            burned = self.deck.burn_one()
            self._viz("deck", "pop", "burn", burned.label,
                      hidden=not (self.practice or self.settings.demo_mode))
            self._viz("burn", "push", "burn card",
                      burned.label if (self.practice or self.settings.demo_mode) else None,
                      hidden=not (self.practice or self.settings.demo_mode))
            cards = [self.deck.deal() for _ in range(3)]
            for card in cards:
                self._viz("deck", "pop", "deal flop", card.label, hidden=False)
            self.community.extend(cards)
            self.street = "flop"
            label = "Flop: " + " ".join(c.label for c in cards)
        elif self.street == "flop":
            burned = self.deck.burn_one()
            self._viz("deck", "pop", "burn", burned.label,
                      hidden=not (self.practice or self.settings.demo_mode))
            self._viz("burn", "push", "burn card",
                      burned.label if (self.practice or self.settings.demo_mode) else None,
                      hidden=not (self.practice or self.settings.demo_mode))
            card = self.deck.deal()
            self._viz("deck", "pop", "deal turn", card.label)
            self.community.append(card)
            self.street = "turn"
            label = f"Turn: {card.label}"
        elif self.street == "turn":
            burned = self.deck.burn_one()
            self._viz("deck", "pop", "burn", burned.label,
                      hidden=not (self.practice or self.settings.demo_mode))
            self._viz("burn", "push", "burn card",
                      burned.label if (self.practice or self.settings.demo_mode) else None,
                      hidden=not (self.practice or self.settings.demo_mode))
            card = self.deck.deal()
            self._viz("deck", "pop", "deal river", card.label)
            self.community.append(card)
            self.street = "river"
            label = f"River: {card.label}"
        else:
            return
        self.phase = self.street
        for player in self._in_hand():
            player.bet = 0
            player.acted = False
            player.short_call_only = False
        self.current_bet = 0
        self.min_raise = self.settings.big_blind
        self._auto_record(self.street, label)
        self.actor_seat = None
        self.turn_deadline = None

    def _run_out_board(self) -> None:
        while self.street != "river":
            self._refund_uncalled()
            self._deal_next_street()
        self._refund_uncalled()
        self._showdown()

    def _end_street(self) -> None:
        if self.phase not in ACTIVE_PHASES:
            return
        self._refund_uncalled()
        active = self._active()
        if len(active) <= 1:
            if active:
                self._finish_fold_win(active[0])
            return
        if self.street == "river":
            self._showdown()
            return
        self._deal_next_street()
        pending = self._pending_actors()
        if not pending:
            # Everyone is all-in or only one player can act with no bet due.
            self._run_out_board()
            return
        first = self._next_player_after(self.dealer_seat, pending)  # type: ignore[arg-type]
        if first is None:
            first = pending[0]
        self._set_actor(first.seat)

    # --------------------------------------------------------------- endings
    def _clear_contributions(self) -> None:
        for player in self._seated():
            player.bet = 0
            player.contributed = 0

    def _record_completed_hand(self, reason: str, pot: int, hand_name: Optional[str]) -> None:
        winners = []
        for entry in (self.result or {}).get("winners", []):
            winners.append({
                "seat": entry["seat"],
                "name": entry["name"],
                "amount": entry["amount"],
                "hand_name": entry.get("hand_name"),
            })
        summary = HandSummary(
            hand_no=self.hand_no,
            winners=winners,
            amount=pot,
            reason=reason,
            hand_name=hand_name,
            board=[c.label for c in self.community],
            players=[p.name for p in self._in_hand()],
            at=time.time(),
        )
        self.hand_history.push(summary)
        self._viz("history", "push", f"Hand #{self.hand_no}", summary.hand_name)
        self._auto_record("win", (self.result or {}).get("headline", "Hand complete"))

    def check_chips(self) -> bool:
        seated_total = sum(p.chips for p in self._seated())
        if self.phase in ACTIVE_PHASES:
            seated_total += sum(p.contributed for p in self._in_hand())
        return seated_total == self.chip_total

    def _finish_hand_common(self) -> None:
        self.phase = "hand_over"
        self.actor_seat = None
        self.turn_started = None
        self.turn_deadline = None
        for player in self._seated():
            if player.chips <= 0 and not player.leaving:
                player.sitting_out = True
        self._clear_contributions()
        self._finalize_leavers()
        if not self.check_chips():
            self.message = "WARNING: chip accounting mismatch detected."
        self._bump()

    def _finish_fold_win(self, winner: Player) -> None:
        pot = sum(p.contributed for p in self._in_hand())
        winner.chips += pot
        winner.is_winner = True
        winner.won = pot
        winner.last_action = f"Wins {pot}"
        self.result = {
            "reason": "fold",
            "headline": f"{winner.name} wins {pot}",
            "pot": pot,
            "message": "Everyone else folded — no cards revealed.",
            "winners": [{
                "seat": winner.seat,
                "name": winner.name,
                "amount": pot,
                "hand_name": None,
                "cards": [],
                "best_five": [],
            }],
            "revealed": [],
            "pot_layers": [],
        }
        self.message = f"{winner.name} wins {pot} — everyone folded."
        self._record_completed_hand("fold", pot, None)
        self._finish_hand_common()

    def _showdown(self) -> None:
        self._refund_uncalled()
        active = self._active()
        if len(active) == 1:
            self._finish_fold_win(active[0])
            return
        if len(self.community) < 5:
            # Defensive: never show down an incomplete board.
            self._run_out_board()
            return

        contributions = {p.seat: p.contributed for p in self._in_hand()}
        folded = {p.seat for p in self._in_hand() if p.folded}
        layers = build_pots(contributions, folded)
        self.pot_stack = PotStack()
        for layer in layers:
            self.pot_stack.push_layer(layer)
            self._viz("pot", "push", layer.label, f"{layer.amount} chips")

        evaluations: dict[int, HandValue] = {}
        for player in active:
            if len(player.cards) != 2:
                raise GameError(f"{player.name} does not have two hole cards at showdown.")
            evaluations[player.seat] = evaluate(player.cards + self.community)

        pot_total = sum(contributions.values())
        awards: dict[int, int] = {}
        layer_results: list[dict] = []
        for layer in reversed(layers):  # top-down: side pots first
            contenders = [seat for seat in layer.eligible if seat in evaluations]
            if not contenders:
                contenders = list(evaluations.keys())
            best_key = max(evaluations[seat].key for seat in contenders)
            winner_seats = [seat for seat in contenders if evaluations[seat].key == best_key]
            winner_seats.sort(key=self._clockwise_key)
            shares = split_pot(layer.amount, winner_seats)
            for seat, amount in shares.items():
                awards[seat] = awards.get(seat, 0) + amount
            layer_results.append({
                "label": layer.label,
                "amount": layer.amount,
                "eligible": list(layer.eligible),
                "winners": [
                    {"seat": seat, "name": self.seats[seat].name,
                     "amount": shares.get(seat, 0),
                     "hand_name": evaluations[seat].name}
                    for seat in winner_seats
                ],
            })
            self._viz("pot", "pop", f"Award {layer.label}", f"{layer.amount} chips")

        winners_payload = []
        for seat, amount in sorted(awards.items(), key=lambda item: (-item[1], item[0])):
            player = self.seats[seat]
            assert player is not None
            player.chips += amount
            player.is_winner = True
            player.won = amount
            player.last_action = f"Wins {amount}"
            value = evaluations[seat]
            winners_payload.append({
                "seat": seat,
                "name": player.name,
                "amount": amount,
                "hand_name": value.name,
                "cards": [card.to_dict() for card in player.cards],
                "best_five": [card.to_dict() for card in value.cards],
            })

        revealed = []
        for player in active:
            value = evaluations[player.seat]
            revealed.append({
                "seat": player.seat,
                "name": player.name,
                "cards": [card.to_dict() for card in player.cards],
                "hand_name": value.name,
                "best_five": [card.to_dict() for card in value.cards],
            })

        if len(winners_payload) == 1:
            top = winners_payload[0]
            headline = f"{top['name']} wins {pot_total} with {top['hand_name']}"
            message = headline
        elif len({w["amount"] for w in winners_payload}) == 1:
            names = " & ".join(w["name"] for w in winners_payload)
            headline = f"Split pot — {names} share {pot_total}"
            message = headline
        else:
            parts = " · ".join(f"{w['name']} {w['amount']}" for w in winners_payload)
            headline = f"Pots awarded — {parts}"
            message = headline
        self.result = {
            "reason": "showdown",
            "headline": headline,
            "pot": pot_total,
            "message": message,
            "winners": winners_payload,
            "revealed": revealed,
            "pot_layers": layer_results,
        }
        best_name = winners_payload[0]["hand_name"] if winners_payload else None
        self.message = message
        self._record_completed_hand("showdown", pot_total, best_name)
        self._finish_hand_common()

    # ------------------------------------------------------------- timeout etc.
    def tick(self, now: Optional[float] = None) -> bool:
        """Advance auto-actions for disconnects/timers.  Called by the room ticker."""
        now = time.time() if now is None else now
        changed = False
        for _ in range(8):
            if self.phase not in ACTIVE_PHASES or self.actor_seat is None:
                break
            player = self.player_at(self.actor_seat)
            if player is None:
                self.actor_seat = None
                break
            deadline = self.turn_deadline
            if not player.connected:
                disconnected_deadline = (player.disconnected_at or now) + 2.0
                deadline = disconnected_deadline if deadline is None else min(deadline, disconnected_deadline)
            if deadline is None or now < deadline:
                break
            to_call = max(0, self.current_bet - player.bet)
            action = "check" if to_call == 0 else "fold"
            try:
                self.act(player.id, action, _auto=True)
                changed = True
            except (ActionError, GameError):
                # Never freeze: force-fold as a last resort.
                try:
                    self.act(player.id, "fold", _auto=True)
                    changed = True
                except (ActionError, GameError):
                    self._set_actor(None)
                    break
        return changed

    def mark_connected(self, player_id: str) -> None:
        player = next((p for p in self._seated() if p.id == player_id), None)
        if player and not player.connected:
            player.connected = True
            player.disconnected_at = 0.0
            self.message = f"{player.name} reconnected."
            self._bump()

    def mark_disconnected(self, player_id: str) -> None:
        player = next((p for p in self._seated() if p.id == player_id), None)
        if player and player.connected:
            player.connected = False
            player.disconnected_at = time.time()
            self.message = f"{player.name} disconnected — auto check/fold soon."
            self._bump()

    # -------------------------------------------------------------- undo/peek
    @property
    def demo_enabled(self) -> bool:
        return self.practice or self.settings.demo_mode

    def _require_host(self, requester_id: str) -> None:
        if self.practice:
            return
        if requester_id != self.host_id:
            raise GameError("Only the host can do that.")

    def undo(self, requester_id: str) -> dict:
        self._require_host(requester_id)
        if not self.demo_enabled:
            raise GameError("Undo is only available in Demo/Practice mode.")
        record = self.action_stack.pop_undoable()
        if record is None:
            raise GameError("Nothing to undo.")
        self._restore(record.snapshot)
        self.message = f"Undo: {record.label}"
        self._viz("action", "pop", f"undo → {record.label}", record.kind)
        self._bump()
        return record.summary()

    def peek_deck(self, requester_id: str) -> dict:
        self._require_host(requester_id)
        if not self.demo_enabled:
            raise GameError("Peeking at the deck is only available in Demo/Practice mode.")
        if self.deck.remaining <= 0:
            raise GameError("The deck is empty.")
        card = self.deck.peek_top()
        self._viz("deck", "peek", "peek()", card.label)
        self.message = f"Demo peek: next card is {card.label}."
        self._bump()
        return card.to_dict()

    # ------------------------------------------------------------ table admin
    def update_settings(self, requester_id: str, patch: dict) -> TableSettings:
        self._require_host(requester_id)
        if self.phase in ACTIVE_PHASES:
            raise GameError("Settings can only be changed between hands.")
        merged = self.settings.as_dict()
        for key in merged:
            if key in patch:
                merged[key] = patch[key]
        new_settings = TableSettings.from_dict(merged)
        if new_settings.max_players < len(self._seated()):
            raise GameError("Reduce seats only after players leave; too many seats are occupied.")
        if new_settings.max_players > len(self.seats):
            self.seats.extend([None] * (new_settings.max_players - len(self.seats)))
        elif new_settings.max_players < len(self.seats):
            for seat in self.seats[new_settings.max_players:]:
                if seat is not None:
                    raise GameError("Cannot remove seats that are occupied.")
            self.seats = self.seats[:new_settings.max_players]
        self.settings = new_settings
        self.min_raise = self.settings.big_blind
        self.message = "Table settings updated."
        self._bump()
        return self.settings

    def set_sit_out(self, player_id: str, out: bool) -> dict:
        player = self._player(player_id)
        if self.phase in ACTIVE_PHASES and out and player.in_hand and not player.folded:
            player.sitting_out = True
            self.message = f"{player.name} will sit out from the next hand."
        else:
            player.sitting_out = bool(out)
            player.waiting = False
            self.message = f"{player.name} is {'sitting out' if out else 'sitting in'}."
        self._bump()
        return {"sitting_out": player.sitting_out}

    def rebuy(self, player_id: str) -> dict:
        player = self._player(player_id)
        if self.phase in ACTIVE_PHASES:
            raise GameError("Rebuy between hands only.")
        if player.chips >= self.settings.big_blind:
            raise GameError("Rebuy is only available when you have less than a big blind.")
        player.chips += self.settings.starting_chips
        self.chip_total += self.settings.starting_chips
        player.sitting_out = False
        player.waiting = False
        self.message = f"{player.name} rebuys for {self.settings.starting_chips}."
        self._bump()
        return {"chips": player.chips}

    def _resume_after_external_fold(self) -> None:
        active = self._active()
        if not active:
            return
        if len(active) == 1:
            self._finish_fold_win(active[0])
            return
        pending = self._pending_actors()
        if not pending:
            if self.actor_seat is not None:
                self._end_street()
            return
        current = self.player_at(self.actor_seat) if self.actor_seat is not None else None
        if current is None or current not in pending:
            nxt = self._next_player_after(self.actor_seat if self.actor_seat is not None else self.dealer_seat,
                                          pending)  # type: ignore[arg-type]
            if nxt is not None:
                self._set_actor(nxt.seat)

    def leave(self, player_id: str) -> None:
        player = self._player(player_id)
        player.leaving = True
        player.sitting_out = True
        was_host = player.id == self.host_id
        # A player who is only waiting (not dealt into the running hand) can
        # leave immediately.
        if self.phase in ACTIVE_PHASES and not player.in_hand:
            seat = player.seat
            self.chip_total -= player.chips
            self.seats[seat] = None
            self.removed_ids.append(player.id)
            if was_host:
                self._promote_host(seat)
            self.message = f"{player.name} left the table."
            self._bump()
            return
        was_actor = self.phase in ACTIVE_PHASES and self.actor_seat == player.seat
        if self.phase in ACTIVE_PHASES and player.in_hand and not player.folded:
            if was_actor:
                player.leaving = True
                try:
                    self.act(player.id, "fold")
                except (ActionError, GameError):
                    player.folded = True
                    self._advance_after_action(player.seat)
            else:
                player.folded = True
                player.acted = True
                player.last_action = "Fold (left)"
                self._auto_record("fold", f"{player.name} folds (left the table)")
                if len(self._active()) == 1:
                    self._finish_fold_win(self._active()[0])
                else:
                    self._resume_after_external_fold()
        self._finalize_leavers()
        self._bump()

    # ------------------------------------------------------------------- state
    def _cards_payload(self, player: Player, viewer_id: Optional[str],
                       practice_view: bool) -> list[dict]:
        if not player.cards:
            return []
        visible = practice_view or (viewer_id is not None and player.id == viewer_id)
        if not visible and player.seat in self._revealed_seats():
            visible = True
        if visible:
            return [card.to_dict() for card in player.cards]
        return [{"hidden": True} for _ in player.cards]

    def state(self, viewer_id: Optional[str] = None, practice_view: bool = False,
              spectator: bool = False) -> dict:
        viewer_player = None
        for player in self._seated():
            if player.id == viewer_id:
                viewer_player = player
                break
        active = self._active()
        pot_total = sum(p.contributed for p in self._in_hand())
        folded = {p.seat for p in self._in_hand() if p.folded}
        preview_layers = []
        if pot_total:
            preview_layers = [layer.to_dict() for layer in build_pots(
                {p.seat: p.contributed for p in self._in_hand() if p.contributed > 0}, folded
            )][::-1]

        seats_payload = []
        for player in self._seated_sorted():
            is_me = viewer_id is not None and player.id == viewer_id
            payload = {
                "seat": player.seat,
                "name": player.name,
                "chips": player.chips,
                "bet": player.bet,
                "contributed": player.contributed,
                "folded": player.folded,
                "all_in": player.all_in,
                "in_hand": player.in_hand,
                "sitting_out": player.sitting_out,
                "waiting": player.waiting,
                "connected": player.connected,
                "leaving": player.leaving,
                "is_host": player.id == self.host_id,
                "is_me": is_me,
                "is_dealer": player.seat == self.dealer_seat,
                "is_sb": player.seat == self.sb_seat,
                "is_bb": player.seat == self.bb_seat,
                "last_action": player.last_action,
                "is_winner": player.is_winner,
                "won": player.won,
                "cards": self._cards_payload(player, viewer_id, practice_view),
                "card_count": len(player.cards),
            }
            seats_payload.append(payload)

        legal = None
        actor = self.player_at(self.actor_seat) if self.actor_seat is not None else None
        can_see_legal = practice_view or (
            viewer_player is not None and actor is not None and viewer_player.seat == actor.seat
        )
        if can_see_legal and actor is not None and self.phase in ACTIVE_PHASES:
            legal = self.legal_actions(actor)
            legal["actor_seat"] = actor.seat
            legal["actor_name"] = actor.name

        deck_top = None
        burn_top = None
        if self.demo_enabled:
            try:
                deck_top = self.deck.peek_top().to_dict()
            except Exception:
                deck_top = None
            try:
                burn_top = self.deck.burn.peek().to_dict()
            except Exception:
                burn_top = None

        host_player = next((p for p in self._seated() if p.id == self.host_id), None)
        result = copy.deepcopy(self.result) if self.result else None
        started = self.hand_no > 0
        can_start = (
            self.phase not in ACTIVE_PHASES
            and len(self._eligible_players(mark=False)) >= max(2, self.settings.min_players)
        )
        viewer_is_host = practice_view or (viewer_id is not None and viewer_id == self.host_id)
        now = time.time()
        turn_remaining = (
            max(0.0, self.turn_deadline - now)
            if self.turn_deadline is not None and self.phase in ACTIVE_PHASES
            else None
        )
        return {
            "phase": self.phase,
            "street": self.street,
            "hand_no": self.hand_no,
            "started": started,
            "message": self.message,
            "version": self.version,
            "server_time": time.time(),
            "practice": self.practice,
            "demo_enabled": self.demo_enabled,
            "table": {
                **self.settings.as_dict(),
                "host_id": self.host_id,
                "host_name": host_player.name if host_player else None,
            },
            "seats": seats_payload,
            "community": [card.to_dict() for card in self.community],
            "pot": {
                "total": pot_total,
                "layers_top_first": preview_layers,
                "resolved": copy.deepcopy(self.pot_stack.to_dict()["layers_top_first"])
                if self.pot_stack.size() else [],
            },
            "current": {
                "actor_seat": self.actor_seat,
                "actor_name": actor.name if actor else None,
                "current_bet": self.current_bet,
                "min_raise": self.min_raise,
                "big_blind": self.settings.big_blind,
                "small_blind": self.settings.small_blind,
                "turn_started": self.turn_started,
                "turn_deadline": self.turn_deadline,
                "turn_remaining": turn_remaining,
                "can_act": len([p for p in self._actors()]),
                "active_players": len(active),
            },
            "legal": legal,
            "result": result,
            "viewer": {
                "player_id": viewer_id,
                "seat": viewer_player.seat if viewer_player else None,
                "is_seated": viewer_player is not None,
                "is_spectator": spectator and viewer_player is None,
                "is_host": viewer_is_host,
                "is_controller": practice_view,
                "chips": viewer_player.chips if viewer_player else 0,
                "sitting_out": viewer_player.sitting_out if viewer_player else False,
            },
            "hand_history": self.hand_history.top_first(10),
            "action_log": self.action_stack.recent(24),
            "viz": {
                "deck": {
                    "size": self.deck.remaining,
                    "top": deck_top,
                    "hidden_top": not self.demo_enabled,
                },
                "burn": {
                    "size": self.deck.burn_count,
                    "top": burn_top,
                    "hidden_top": not self.demo_enabled,
                },
                "action": {
                    "size": self.action_stack.size(),
                    "top": self.action_stack.top(),
                },
                "history": {"size": self.hand_history.size()},
                "pots": self.pot_stack.to_dict(),
                "events": copy.deepcopy(self.viz_events[-40:]),
                "chip_total": self.chip_total,
            },
            "can_start": can_start and viewer_is_host,
            "can_next": (
                self.phase not in ACTIVE_PHASES
                and started
                and len(self._eligible_players(mark=False)) >= max(2, self.settings.min_players)
            ),
            "total_chips": self.chip_total,
            "undo_available": self.demo_enabled and viewer_is_host and not self.action_stack.is_empty(),
            "seats_available": [i for i, seat in enumerate(self.seats) if seat is None],
        }

    def summary(self) -> dict:
        return {
            "phase": self.phase,
            "hand_no": self.hand_no,
            "players": len(self._seated()),
            "max_players": self.settings.max_players,
            "name": self.settings.name,
            "private": self.settings.private,
            "practice": self.practice,
            "blinds": [self.settings.small_blind, self.settings.big_blind],
            "starter": self.settings.starting_chips,
            "demo_mode": self.settings.demo_mode,
            "version": self.version,
        }
