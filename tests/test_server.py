import json
import threading
import unittest
import urllib.error
import urllib.request

from pokerstack.server import make_server


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd, cls.app = make_server("127.0.0.1", 0)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.app.stop_ticker()
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def request(self, method, path, data=None, token=None):
        body = json.dumps(data).encode() if data is not None else None
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=body, method=method
        )
        if body is not None:
            request.add_header("Content-Type", "application/json")
        if token:
            request.add_header("X-Table-Token", token)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())

    def state(self, code, token):
        status, payload = self.request("GET", f"/api/state?code={code}", token=token)
        self.assertEqual(status, 200, payload)
        return payload["data"]

    def test_full_two_player_http_flow(self):
        # Health
        status, health = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(health["ok"])

        # Create an open table so it is listed in the lobby.
        status, created = self.request("POST", "/api/create", {
            "name": "Alice",
            "table_name": "HTTP Gold",
            "max_players": 2,
            "min_players": 2,
            "starting_chips": 1000,
            "small_blind": 5,
            "big_blind": 10,
            "turn_seconds": 0,
            "private": False,
            "late_join": True,
            "spectators": True,
        })
        self.assertEqual(status, 200, created)
        code = created["data"]["code"]
        host_token = created["data"]["token"]
        self.assertEqual(len(code), 5)

        status, tables = self.request("GET", "/api/tables")
        self.assertEqual(status, 200)
        self.assertIn(code, [t["code"] for t in tables["data"]["tables"]])

        # Join second player.
        status, joined = self.request("POST", "/api/join", {"code": code, "name": "Bob"})
        self.assertEqual(status, 200, joined)
        guest_token = joined["data"]["token"]

        host_state = self.state(code, host_token)
        self.assertTrue(host_state["room"]["is_host"])
        self.assertFalse(host_state["started"])

        status, started = self.request("POST", "/api/start", {"code": code}, token=host_token)
        self.assertEqual(status, 200, started)
        host_state = self.state(code, host_token)
        guest_state = self.state(code, guest_token)
        self.assertEqual(host_state["phase"], "preflop")
        self.assertEqual(host_state["hand_no"], 1)
        self.assertTrue(host_state["room"]["is_host"])
        self.assertFalse(guest_state["room"]["is_host"])

        # Private cards: each sees their own only.
        host_seat = next(s for s in host_state["seats"] if s["is_me"])
        opponent_in_host_view = next(s for s in host_state["seats"] if not s["is_me"])
        guest_seat = next(s for s in guest_state["seats"] if s["is_me"])
        self.assertEqual(len(host_seat["cards"]), 2)
        self.assertTrue(all("code" in c for c in host_seat["cards"]))
        self.assertTrue(all(c.get("hidden") for c in opponent_in_host_view["cards"]))
        self.assertTrue(all("code" in c for c in guest_seat["cards"]))
        guest_codes = [c["code"] for c in guest_seat["cards"]]
        serialized = json.dumps(host_state)
        for card_code in guest_codes:
            self.assertNotIn(f'"code":"{card_code}"', serialized)

        # Spectator cannot see private cards.
        status, spec = self.request("POST", "/api/join",
                                    {"code": code, "name": "Watcher", "spectator": True})
        self.assertEqual(status, 200, spec)
        spectator_state = self.state(code, spec["data"]["token"])
        self.assertTrue(spectator_state["room"]["is_spectator"])
        self.assertTrue(all(card.get("hidden")
                            for seat in spectator_state["seats"]
                            for card in seat["cards"]))

        # Acting out of turn is rejected with a clear message.
        status, error = self.request("POST", "/api/act",
                                     {"code": code, "action": "fold"}, token=guest_token)
        self.assertEqual(status, 400)
        self.assertIn("not your turn", error["error"].lower())

        # Play checks/calls to showdown.
        actions = 0
        while actions < 40:
            state = self.state(code, host_token)
            if state["phase"] not in ("preflop", "flop", "turn", "river"):
                break
            actor_seat = state["current"]["actor_seat"]
            token = host_token if actor_seat == host_seat["seat"] else guest_token
            actor_state = self.state(code, token)
            legal = actor_state["legal"]
            action = "check" if legal["check"]["allowed"] else "call"
            status, result = self.request("POST", "/api/act", {
                "code": code, "action": action,
            }, token=token)
            self.assertEqual(status, 200, result)
            actions += 1
        final = self.state(code, host_token)
        self.assertEqual(final["phase"], "hand_over")
        self.assertEqual(sum(seat["chips"] for seat in final["seats"]), 2000)
        self.assertTrue(final["result"]["winners"])
        self.assertEqual(len(final["result"]["revealed"]), 2)
        # Showdown reveals cards to opponents.
        revealed_state = self.state(code, host_token)
        self.assertFalse(any(c.get("hidden") for s in revealed_state["seats"]
                             for c in s["cards"]))

        # Bad token
        status, error = self.request("GET", f"/api/state?code={code}", token="nope")
        self.assertEqual(status, 401)
        status, error = self.request("GET", "/api/state?code=ZZZZZ", token=host_token)
        self.assertEqual(status, 404)

    def test_practice_mode_http_and_undo(self):
        status, created = self.request("POST", "/api/practice", {
            "players": 3, "starting_chips": 1000,
        })
        self.assertEqual(status, 200, created)
        code = created["data"]["code"]
        token = created["data"]["token"]
        state = self.state(code, token)
        self.assertTrue(state["practice"])
        self.assertTrue(state["demo_enabled"])
        self.assertTrue(state["viewer"]["is_controller"])
        self.assertEqual(len(state["seats"]), 3)
        self.assertTrue(all(len(seat["cards"]) == 2 for seat in state["seats"]))
        # Nobody else's card is hidden in practice mode.
        self.assertFalse(any(card.get("hidden") for seat in state["seats"]
                             for card in seat["cards"]))
        actor_seat = state["current"]["actor_seat"]
        legal = state["legal"]
        action = "check" if legal["check"]["allowed"] else "call"
        status, after = self.request("POST", "/api/act", {
            "code": code, "action": action, "seat": actor_seat,
        }, token=token)
        self.assertEqual(status, 200, after)
        self.assertNotEqual(after["data"]["current"]["actor_seat"], actor_seat)
        status, undone = self.request("POST", "/api/undo", {"code": code}, token=token)
        self.assertEqual(status, 200, undone)
        self.assertEqual(undone["data"]["current"]["actor_seat"], actor_seat)
        status, peek = self.request("POST", "/api/peek", {"code": code}, token=token)
        self.assertEqual(status, 200, peek)
        self.assertIn("code", peek["data"]["card"])


if __name__ == "__main__":
    unittest.main()
