"""Standard-library HTTP server + live state API.

No external dependencies, no build step.  The browser short-polls
``GET /api/state`` (roughly once a second, and immediately after every action),
which keeps the game in sync on phones, laptops and across a LAN.

Privacy is enforced here and in game.state(): each response is built for one
viewer, and only that viewer's hole cards (or showdown cards) are ever sent.
"""

from __future__ import annotations

import json
import mimetypes
import os
import socket
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urlparse

from .betting import ActionError
from .game import GameError, TableSettings
from .rooms import RoomError, RoomManager

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
MAX_BODY = 64 * 1024


class App:
    def __init__(self, web_dir: Optional[Path] = None) -> None:
        self.manager = RoomManager()
        self.web_dir = (web_dir or WEB_DIR).resolve()
        self.started_at = time.time()
        self._ticker: Optional[threading.Thread] = None
        self._ticker_stop = threading.Event()

    def start_ticker(self) -> None:
        if self._ticker is not None:
            return
        def run() -> None:
            while not self._ticker_stop.is_set():
                try:
                    self.manager.tick_all()
                except Exception as exc:
                    print(f"[ticker] {exc}")
                self._ticker_stop.wait(0.4)
        self._ticker = threading.Thread(target=run, name="pokerstack-ticker", daemon=True)
        self._ticker.start()

    def stop_ticker(self) -> None:
        self._ticker_stop.set()


class Handler(BaseHTTPRequestHandler):
    server_version = "KasheRoyale/1.0"
    protocol_version = "HTTP/1.1"
    app: App  # assigned by make_server

    # ------------------------------------------------------------------ output
    def _send(self, status: int, body: bytes, content_type: str,
              extra_headers: Optional[dict[str, str]] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; font-src 'self'; "
            "base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
        )
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self._send(status, data, "application/json; charset=utf-8")

    def _ok(self, data: Any) -> None:
        self._json(200, {"ok": True, "data": data})

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"ok": False, "error": message})

    def _token(self, query: dict) -> str:
        token = self.headers.get("X-Table-Token") or ""
        if not token:
            token = (query.get("token") or [""])[0]
        return token.strip()

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > MAX_BODY:
            raise ValueError("Request body is too large.")
        raw = self.rfile.read(length) if length else b"{}"
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("Invalid JSON body.")
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object.")
        return data

    # ------------------------------------------------------------------ routing
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        if path.startswith("/api/"):
            self._handle_get_api(path, query)
            return
        self._serve_static(path)

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            body = self._body()
        except ValueError as exc:
            self._error(400, str(exc))
            return
        try:
            self._handle_post_api(path, body)
        except RoomError as exc:
            self._error(exc.status, str(exc))
        except (ActionError, GameError) as exc:
            self._error(400, str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            self._error(400, f"Bad request: {exc}")
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[server] unhandled error: {exc!r}")
            self._error(500, "Internal server error.")

    # ---------------------------------------------------------------------- GET
    def _handle_get_api(self, path: str, query: dict) -> None:
        try:
            if path == "/api/health":
                self._ok({
                    "status": "ok",
                    "rooms": len(self.app.manager.rooms),
                    "uptime": round(time.time() - self.app.started_at, 1),
                })
                return
            if path == "/api/tables":
                self._ok({"tables": self.app.manager.open_tables()})
                return
            if path == "/api/state":
                code = (query.get("code") or [""])[0]
                token = self._token(query)
                if not code:
                    self._error(400, "Room code is required.")
                    return
                if not token:
                    self._error(401, "Missing table token.")
                    return
                state = self.app.manager.state(code, token)
                self._ok(state)
                return
            self._error(404, "Unknown API endpoint.")
        except RoomError as exc:
            self._error(exc.status, str(exc))
        except Exception as exc:  # pragma: no cover
            print(f"[server] GET error: {exc!r}")
            self._error(500, "Internal server error.")

    # --------------------------------------------------------------------- POST
    def _handle_post_api(self, path: str, body: dict) -> None:
        manager = self.app.manager
        if path == "/api/create":
            name = str(body.get("name") or "Host")
            settings_body = dict(body)
            settings_body["name"] = body.get("table_name") or "Royal Table"
            settings = TableSettings.from_dict(settings_body)
            room, token = manager.create_room(name, settings)
            state = room.state_for(token)
            self._ok({"code": room.code, "token": token, "state": state})
            return
        if path == "/api/join":
            code = str(body.get("code") or "")
            name = str(body.get("name") or "Player")
            spectator = bool(body.get("spectator", False))
            room, token = manager.join(code, name, spectator)
            state = room.state_for(token)
            self._ok({"code": room.code, "token": token, "state": state})
            return
        if path == "/api/practice":
            name = str(body.get("name") or "Practice Table")
            players = int(body.get("players", 2))
            starting = int(body.get("starting_chips", 1000))
            room, token = manager.create_practice(name, players, starting)
            state = room.state_for(token)
            self._ok({"code": room.code, "token": token, "state": state})
            return

        code = str(body.get("code") or "").strip().upper()
        if not code:
            self._error(400, "Room code is required.")
            return
        token = self._token({}) or str(body.get("token") or "")
        if not token:
            self._error(401, "Missing table token.")
            return
        room = manager.room(code)
        if path == "/api/act":
            state = room.act(
                token,
                str(body.get("action") or ""),
                amount=body.get("amount"),
                seat=body.get("seat"),
            )
            self._ok(state)
            return
        if path == "/api/start":
            self._ok(room.start(token))
            return
        if path == "/api/next":
            self._ok(room.next_hand(token))
            return
        if path == "/api/sit":
            self._ok(room.sit(token, bool(body.get("out", True))))
            return
        if path == "/api/rebuy":
            self._ok(room.rebuy(token))
            return
        if path == "/api/leave":
            self._ok(room.leave(token))
            return
        if path == "/api/settings":
            patch = body.get("settings")
            if not isinstance(patch, dict):
                raise ValueError("settings must be an object")
            self._ok(room.update_settings(token, patch))
            return
        if path == "/api/undo":
            self._ok(room.undo(token))
            return
        if path == "/api/peek":
            self._ok(room.peek(token))
            return
        self._error(404, "Unknown API endpoint.")

    # ------------------------------------------------------------------- static
    def _serve_static(self, path: str) -> None:
        if path in ("", "/"):
            path = "/index.html"
        relative = path.lstrip("/")
        candidate = (self.app.web_dir / relative).resolve()
        try:
            candidate.relative_to(self.app.web_dir)
        except ValueError:
            self._error(404, "Not found.")
            return
        if not candidate.is_file():
            # Friendly fallback for invite links: /ABC12 -> index.html
            candidate = self.app.web_dir / "index.html"
            if not candidate.is_file():
                self._error(404, "Not found.")
                return
        try:
            data = candidate.read_bytes()
        except OSError:
            self._error(404, "Not found.")
            return
        content_type, _ = mimetypes.guess_type(str(candidate))
        if candidate.suffix == ".js":
            content_type = "text/javascript; charset=utf-8"
        elif candidate.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif candidate.suffix == ".html":
            content_type = "text/html; charset=utf-8"
        elif candidate.suffix == ".svg":
            content_type = "image/svg+xml"
        content_type = content_type or "application/octet-stream"
        self._send(200, data, content_type)

    def log_message(self, format: str, *args: Any) -> None:
        # Keep the console readable; errors are still printed by the handlers.
        if self.path.startswith("/api/health"):
            return
        if self.path.startswith("/api/state"):
            return
        print(f"[http] {self.address_string()} {format % args}")


def make_server(host: str = "0.0.0.0", port: int = 8000,
                app: Optional[App] = None) -> tuple[ThreadingHTTPServer, App]:
    app = app or App()
    handler = type("PokerStackHandler", (Handler,), {"app": app})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    app.start_ticker()
    return server, app


def local_ip() -> str:
    """Best-effort LAN address, without any external dependency."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        finally:
            sock.close()
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"


def find_port(host: str, start: int, attempts: int = 20) -> int:
    for offset in range(attempts):
        port = start + offset
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind((host, port))
            return port
        except OSError:
            continue
        finally:
            probe.close()
    raise RuntimeError(f"No free port found near {start}.")


def _force_utf8_output() -> None:
    """Make sure printing the suit symbols never crashes the launcher.

    On Windows the console defaults to a legacy code page (cp1252, GBK, ...)
    that cannot encode ♠ ♥ ♦ ♣, so ``print()`` raises UnicodeEncodeError as
    soon as stdout is piped, redirected to a file, or run from an IDE.
    Reconfiguring the streams to UTF-8 fixes it everywhere; ``errors="replace"``
    means a bad character degrades to a placeholder instead of killing the server.
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except (ValueError, OSError):  # closed or non-configurable stream
            pass


def main(host: str = "0.0.0.0", port: int = 8000, open_browser: bool = True) -> None:
    _force_utf8_output()
    port = find_port(host, port)
    server, app = make_server(host, port)
    lan = local_ip()
    local_url = f"http://127.0.0.1:{port}/"
    lan_url = f"http://{lan}:{port}/"
    print()
    print("  \u2660 \u2665  Kashe Royale — Royal Texas Hold'em  \u2666 \u2663")
    print("  " + "-" * 52)
    print(f"  Local:   {local_url}")
    print(f"  Network: {lan_url}   (same Wi-Fi, other device)")
    print("  Room codes are shared from inside the lobby.")
    print("  Press Ctrl+C to stop.")
    print()
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(local_url)).start()
    try:
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        print("\n  Shutting down Kashe Royale. Good game.")
    finally:
        app.stop_ticker()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":  # pragma: no cover
    main()
