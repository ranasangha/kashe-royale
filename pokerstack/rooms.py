"""Rooms, seats, sessions, reconnects and the background timer.

A Room wraps one authoritative Game and maps opaque bearer tokens to players
(or spectators).  Short polling calls ``state_for``; a background ticker calls
``tick`` to enforce turn timers and disconnect auto-actions even when nobody
is polling.

Room codes are short, human-friendly and unambiguous (no O/0/I/1).
"""

from __future__ import annotations

import random
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from .game import Game, GameError, TableSettings

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
DISCONNECT_GRACE_SECONDS = 6.0   # no poll for this long -> mark disconnected
ROOM_IDLE_SECONDS = 6 * 60 * 60


class RoomError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class Session:
    token: str
    name: str
    player_id: Optional[str] = None
    spectator: bool = False
    controller: bool = False
    last_seen: float = field(default_factory=time.time)


class Room:
    def __init__(self, code: str, game: Game, practice: bool = False) -> None:
        self.code = code
        self.game = game
        self.practice = practice
        self.tokens: dict[str, Session] = {}
        self.lock = threading.RLock()
        self.created_at = time.time()
        self.last_activity = time.time()
        self.closed = False

    # --------------------------------------------------------------- sessions
    def _session(self, token: str) -> Session:
        session = self.tokens.get(token)
        if session is None:
            raise RoomError("Your session has ended. Rejoin the table.", 401)
        return session

    def add_player_session(self, player_id: str, name: str) -> tuple[str, Session]:
        token = secrets.token_urlsafe(24)
        session = Session(token=token, name=name, player_id=player_id)
        self.tokens[token] = session
        return token, session

    def add_spectator_session(self, name: str) -> tuple[str, Session]:
        token = secrets.token_urlsafe(24)
        session = Session(token=token, name=name, spectator=True)
        self.tokens[token] = session
        return token, session

    def add_controller_session(self, name: str = "Practice") -> tuple[str, Session]:
        token = secrets.token_urlsafe(24)
        session = Session(token=token, name=name, controller=True)
        self.tokens[token] = session
        return token, session

    def _unique_name(self, name: str) -> str:
        clean = (name or "Player").strip()[:18] or "Player"
        taken = {p.name.casefold() for p in self.game._seated()}
        taken.update(s.name.casefold() for s in self.tokens.values() if s.spectator)
        if clean.casefold() not in taken:
            return clean
        for number in range(2, 100):
            candidate = f"{clean} {number}"
            if candidate.casefold() not in taken:
                return candidate
        return clean + " " + secrets.token_hex(2)

    def _sync_tokens_locked(self) -> None:
        removed = self.game.pop_removed_ids()
        if removed:
            for token in list(self.tokens):
                if self.tokens[token].player_id in removed:
                    self.tokens.pop(token, None)

    def player_count(self) -> int:
        return len(self.game._seated())

    def spectator_count(self) -> int:
        return sum(1 for s in self.tokens.values() if s.spectator)

    # ------------------------------------------------------------------- state
    def state_for(self, token: str) -> dict:
        with self.lock:
            session = self._session(token)
            session.last_seen = time.time()
            self._sync_tokens_locked()
            if self.practice:
                viewer_id = "controller"
                state = self.game.state(viewer_id, practice_view=True)
                is_host = True
            else:
                viewer_id = session.player_id
                if viewer_id is not None:
                    self.game.mark_connected(viewer_id)
                state = self.game.state(viewer_id, spectator=session.spectator)
                is_host = bool(viewer_id and viewer_id == self.game.host_id)
            state["room"] = {
                "code": self.code,
                "is_host": is_host,
                "is_controller": self.practice,
                "is_spectator": session.spectator,
                "session_name": session.name,
                "player_count": self.player_count(),
                "spectator_count": self.spectator_count(),
                "practice": self.practice,
                "created_at": self.created_at,
            }
            self.last_activity = time.time()
            return state

    # ------------------------------------------------------------------ actions
    def _actor_id(self, session: Session) -> str:
        if self.practice:
            return "controller"
        if session.spectator or session.player_id is None:
            raise RoomError("Spectators can watch, but cannot act.", 403)
        return session.player_id

    def act(self, token: str, action: str, amount=None, seat=None) -> dict:
        with self.lock:
            session = self._session(token)
            session.last_seen = time.time()
            actor_id = self._actor_id(session)
            if self.practice and seat is None:
                seat = self.game.actor_seat
            self.game.act(actor_id, action, amount=amount, seat=seat)
            self._sync_tokens_locked()
            self.last_activity = time.time()
            return self.state_for(token)

    def start(self, token: str) -> dict:
        with self.lock:
            session = self._session(token)
            session.last_seen = time.time()
            self.game.start_game(self._actor_id(session))
            self.last_activity = time.time()
            return self.state_for(token)

    def next_hand(self, token: str) -> dict:
        with self.lock:
            session = self._session(token)
            session.last_seen = time.time()
            requester = self._actor_id(session)
            self.game.next_hand(requester)
            self.last_activity = time.time()
            return self.state_for(token)

    def sit(self, token: str, out: bool) -> dict:
        with self.lock:
            session = self._session(token)
            session.last_seen = time.time()
            if session.spectator or session.player_id is None:
                raise RoomError("Spectators have no seat to sit in or out.", 403)
            self.game.set_sit_out(session.player_id, out)
            self.last_activity = time.time()
            return self.state_for(token)

    def rebuy(self, token: str) -> dict:
        with self.lock:
            session = self._session(token)
            session.last_seen = time.time()
            if session.spectator or session.player_id is None:
                raise RoomError("Spectators cannot rebuy.", 403)
            self.game.rebuy(session.player_id)
            self.last_activity = time.time()
            return self.state_for(token)

    def update_settings(self, token: str, patch: dict) -> dict:
        with self.lock:
            session = self._session(token)
            session.last_seen = time.time()
            self.game.update_settings(self._actor_id(session), patch)
            self.last_activity = time.time()
            return self.state_for(token)

    def undo(self, token: str) -> dict:
        with self.lock:
            session = self._session(token)
            session.last_seen = time.time()
            self.game.undo(self._actor_id(session))
            self.last_activity = time.time()
            return self.state_for(token)

    def peek(self, token: str) -> dict:
        with self.lock:
            session = self._session(token)
            session.last_seen = time.time()
            card = self.game.peek_deck(self._actor_id(session))
            self.last_activity = time.time()
            return {"card": card, "state": self.state_for(token)}

    def leave(self, token: str) -> dict:
        with self.lock:
            session = self._session(token)
            session.last_seen = time.time()
            if session.controller:
                self.closed = True
                self.tokens.pop(token, None)
                return {"closed": True}
            if session.spectator:
                self.tokens.pop(token, None)
                self.last_activity = time.time()
                return {"closed": False}
            assert session.player_id is not None
            self.game.leave(session.player_id)
            self.tokens.pop(token, None)
            self._sync_tokens_locked()
            if not any(s.player_id for s in self.tokens.values()):
                # No players remain; spectators can linger briefly, but the
                # room is no longer useful.
                self.closed = True
            self.last_activity = time.time()
            return {"closed": self.closed}

    # ------------------------------------------------------------------ timers
    def check_connections(self, now: float) -> None:
        for session in list(self.tokens.values()):
            if session.controller or session.spectator or not session.player_id:
                continue
            if now - session.last_seen <= DISCONNECT_GRACE_SECONDS:
                continue
            player = next((p for p in self.game._seated() if p.id == session.player_id), None)
            if player is not None and player.connected:
                self.game.mark_disconnected(player.id)

    def tick(self, now: float) -> None:
        with self.lock:
            self.check_connections(now)
            self.game.tick(now)
            self._sync_tokens_locked()

    # -------------------------------------------------------------------- info
    def summary(self) -> dict:
        players = self.game._seated()
        return {
            "code": self.code,
            "name": self.game.settings.name,
            "players": len(players),
            "max_players": self.game.settings.max_players,
            "blinds": [self.game.settings.small_blind, self.game.settings.big_blind],
            "starting_chips": self.game.settings.starting_chips,
            "phase": self.game.phase,
            "started": self.game.hand_no > 0,
            "practice": self.practice,
            "private": self.game.settings.private,
            "demo_mode": self.game.settings.demo_mode,
            "created_at": self.created_at,
        }


class RoomManager:
    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}
        self.lock = threading.RLock()

    def _new_code(self) -> str:
        while True:
            code = "".join(random.choice(CODE_ALPHABET) for _ in range(5))
            with self.lock:
                if code not in self.rooms:
                    return code

    def create_room(self, host_name: str, settings: TableSettings) -> tuple[Room, str]:
        code = self._new_code()
        player_id = secrets.token_hex(10)
        game = Game(settings, host_id=player_id)
        player = game.add_player(player_id, host_name or "Host")
        room = Room(code, game)
        token, _ = room.add_player_session(player_id, player.name)
        with self.lock:
            self.rooms[code] = room
        return room, token

    def create_practice(self, name: str = "Practice Table",
                        player_total: int = 2,
                        starting_chips: int = 1000) -> tuple[Room, str]:
        count = max(2, min(6, int(player_total)))
        settings = TableSettings(
            name=name or "Practice Table",
            max_players=count,
            min_players=2,
            starting_chips=starting_chips,
            small_blind=5,
            big_blind=10,
            turn_seconds=0,
            late_join=False,
            spectators=False,
            private=True,
            demo_mode=True,
        )
        game = Game(settings, host_id="controller", practice=True)
        for index in range(count):
            game.add_player(f"practice-{index + 1}", f"Player {index + 1}", settings.starting_chips)
        game.start_game("controller")
        room = Room(self._new_code(), game, practice=True)
        token, _ = room.add_controller_session("Practice")
        with self.lock:
            self.rooms[room.code] = room
        return room, token

    def room(self, code: str) -> Room:
        code = (code or "").strip().upper()
        with self.lock:
            room = self.rooms.get(code)
        if room is None or room.closed:
            raise RoomError("Table not found. Check the room code.", 404)
        return room

    def join(self, code: str, name: str, spectator: bool = False) -> tuple[Room, str]:
        room = self.room(code)
        with room.lock:
            if room.practice:
                raise RoomError("Practice tables cannot be joined.", 403)
            if spectator:
                if not room.game.settings.spectators:
                    raise RoomError("This table does not allow spectators.", 403)
                token, _ = room.add_spectator_session(room._unique_name(name or "Spectator"))
                room.last_activity = time.time()
                return room, token
            if room.game.phase not in ("preflop", "flop", "turn", "river"):
                # joining between hands is always allowed if a seat is free
                pass
            elif not room.game.settings.late_join:
                raise RoomError("Late joining is disabled at this table.", 403)
            player_id = secrets.token_hex(10)
            player_name = room._unique_name(name or "Player")
            player = room.game.add_player(player_id, player_name)
            token, _ = room.add_player_session(player.id, player.name)
            room.last_activity = time.time()
            return room, token

    def state(self, code: str, token: str) -> dict:
        room = self.room(code)
        return room.state_for(token)

    def open_tables(self) -> list[dict]:
        with self.lock:
            rooms = list(self.rooms.values())
        tables = []
        for room in rooms:
            if room.closed or room.practice:
                continue
            try:
                with room.lock:
                    if room.game.settings.private:
                        continue
                    if room.player_count() >= room.game.settings.max_players:
                        continue
                    tables.append(room.summary())
            except Exception:
                continue
        tables.sort(key=lambda t: t["created_at"], reverse=True)
        return tables

    def tick_all(self, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        with self.lock:
            rooms = list(self.rooms.values())
        for room in rooms:
            try:
                room.tick(now)
            except Exception as exc:  # A broken room must never stop the ticker.
                print(f"[room {room.code}] tick error: {exc}")
        with self.lock:
            for code, room in list(self.rooms.items()):
                expired = now - room.last_activity > ROOM_IDLE_SECONDS
                no_sessions = not room.tokens
                if room.closed or expired or no_sessions:
                    self.rooms.pop(code, None)
