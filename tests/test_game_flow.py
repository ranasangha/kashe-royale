import random
import time
import unittest

from pokerstack.betting import ActionError
from pokerstack.cards import parse_cards
from pokerstack.game import Game, GameError, TableSettings


def make_game(players=2, chips=None, demo=False, turn_seconds=0, starting=1000,
              small_blind=5, big_blind=10, min_players=2):
    settings = TableSettings(
        name="Test Table",
        max_players=players,
        min_players=min_players,
        starting_chips=starting,
        small_blind=small_blind,
        big_blind=big_blind,
        turn_seconds=turn_seconds,
        demo_mode=demo,
    )
    game = Game(settings, host_id="p1")
    names = ["Alice", "Bob", "Cara", "Dan", "Eve", "Finn"]
    for index in range(players):
        amount = chips[index] if chips else starting
        game.add_player(f"p{index + 1}", names[index], amount)
    return game


def act(game, action="check", amount=None):
    actor = game.player_at(game.actor_seat)
    assert actor is not None, "No actor"
    return game.act(actor.id, action, amount=amount)


class TestHeadsUpFlow(unittest.TestCase):
    def setUp(self):
        self.game = make_game(2)
        self.order = parse_cards("KS AS KH AH 4C 2C 7D 9S 5D JC 6C 3H")

    def test_blinds_button_and_action_order(self):
        game = self.game
        self.assertTrue(game.start_hand(self.order))
        self.assertEqual(game.dealer_seat, 0)
        self.assertEqual(game.sb_seat, 0)   # heads-up: dealer is small blind
        self.assertEqual(game.bb_seat, 1)
        self.assertEqual(game.actor_seat, 0)  # heads-up: dealer acts first pre-flop
        self.assertEqual(game.player_at(0).cards[0].code, "AS")
        self.assertEqual(game.player_at(1).cards[0].code, "KS")

        game.act("p1", "call")
        self.assertEqual(game.actor_seat, 1)   # big blind still has an option
        game.act("p2", "check")
        self.assertEqual(game.phase, "flop")
        self.assertEqual(game.actor_seat, 1)   # post-flop: first left of dealer

    def test_full_showdown_reveals_and_awards(self):
        game = self.game
        game.start_hand(self.order)
        game.act("p1", "call")
        game.act("p2", "check")
        while game.phase in ("flop", "turn", "river"):
            act(game, "check")
        self.assertEqual(game.phase, "hand_over")
        self.assertEqual([c.code for c in game.community],
                         ["2C", "7D", "9S", "JC", "3H"])
        self.assertEqual(game.result["reason"], "showdown")
        self.assertEqual(game.result["winners"][0]["seat"], 0)
        self.assertEqual(game.player_at(0).chips, 1010)
        self.assertEqual(game.player_at(1).chips, 990)
        self.assertTrue(game.check_chips())
        self.assertEqual(game.hand_history.size(), 1)
        self.assertEqual(game.hand_history.peek().hand_no, 1)
        # Both players' cards are exposed in the showdown result.
        self.assertEqual(len(game.result["revealed"]), 2)
        viewer = game.state("p2")
        self.assertFalse(any(card.get("hidden") for card in viewer["seats"][0]["cards"]))

    def test_fold_win_hides_cards(self):
        game = self.game
        game.start_hand(self.order)
        game.act("p1", "fold")
        self.assertEqual(game.phase, "hand_over")
        self.assertEqual(game.result["reason"], "fold")
        self.assertEqual(game.result["winners"][0]["seat"], 1)
        self.assertEqual(game.result["revealed"], [])
        self.assertEqual(game.player_at(1).chips, 1005)
        self.assertEqual(game.player_at(0).chips, 995)
        viewer = game.state("p1")
        bobs_cards = viewer["seats"][1]["cards"]
        self.assertEqual(bobs_cards, [{"hidden": True}, {"hidden": True}])
        self.assertTrue(game.check_chips())

    def test_privacy_before_showdown(self):
        game = self.game
        game.start_hand(self.order)
        alice_state = game.state("p1")
        alice = next(s for s in alice_state["seats"] if s["seat"] == 0)
        bob = next(s for s in alice_state["seats"] if s["seat"] == 1)
        self.assertEqual([c["code"] for c in alice["cards"]], ["AS", "AH"])
        self.assertTrue(all(c.get("hidden") for c in bob["cards"]))
        serialized = str(alice_state)
        self.assertNotIn('"code":"KS"', serialized)
        self.assertNotIn('"code":"KH"', serialized)

        spectator_state = game.state(None, spectator=True)
        self.assertTrue(all(c.get("hidden") for s in spectator_state["seats"] for c in s["cards"]))

    def test_illegal_actions_rejected(self):
        game = self.game
        game.start_hand(self.order)
        with self.assertRaises(ActionError):
            game.act("p2", "check")            # out of turn
        with self.assertRaises(ActionError):
            game.act("p1", "check")            # facing the big blind
        with self.assertRaises(ActionError):
            game.act("p1", "raise", 15)        # below min raise-to (20)
        game.act("p1", "call")
        game.act("p2", "check")
        with self.assertRaises(ActionError):
            game.act("p1", "call")             # nothing to call
        with self.assertRaises(ActionError):
            game.act("p1", "raise", 10_000)    # more than stack
        self.assertEqual(game.phase, "flop")

    def test_undo_restores_exact_state(self):
        game = make_game(2, demo=True)
        game.start_hand(self.order)
        before_stack = game.action_stack.size()
        before = (game.player_at(0).chips, game.player_at(0).bet,
                  game.current_bet, game.actor_seat, game.phase)
        game.act("p1", "raise", 40)
        self.assertEqual(game.player_at(0).chips, 960)
        result = game.undo("p1")
        self.assertEqual(result["kind"], "raise")
        after = (game.player_at(0).chips, game.player_at(0).bet,
                 game.current_bet, game.actor_seat, game.phase)
        self.assertEqual(before, after)
        self.assertEqual(game.action_stack.size(), before_stack)
        self.assertEqual(game.community, [])
        # Peek is demo-only and must not remove the card.
        card = game.peek_deck("p1")
        self.assertEqual(card["code"], "4C")
        self.assertEqual(game.deck.remaining, 48)
        with self.assertRaises(GameError):
            make_game(2).undo("p1")

    def test_turn_timeout_auto_checks_or_folds(self):
        game = make_game(2, turn_seconds=1)
        game.start_hand(self.order)
        game.tick(time.time() + 5)
        self.assertEqual(game.phase, "hand_over")
        self.assertEqual(game.result["reason"], "fold")
        self.assertEqual(game.player_at(1).chips, 1005)

    def test_disconnect_auto_action_even_without_timer(self):
        game = make_game(2, turn_seconds=0)
        game.start_hand(self.order)
        game.mark_disconnected("p1")
        self.assertFalse(game.player_at(0).connected)
        game.tick(time.time() + 5)
        self.assertEqual(game.phase, "hand_over")
        self.assertEqual(game.result["reason"], "fold")

    def test_settings_between_hands_only(self):
        game = make_game(3)
        with self.assertRaises(GameError):
            game.update_settings("p2", {"name": "Nope"})
        game.update_settings("p1", {"name": "Gold Room", "big_blind": 20, "small_blind": 10})
        self.assertEqual(game.settings.name, "Gold Room")
        game.start_hand()
        with self.assertRaises(GameError):
            game.update_settings("p1", {"name": "Mid-hand"})

    def test_rebuy_and_sit_out(self):
        game = make_game(2)
        game.start_hand(self.order)
        game.act("p1", "fold")
        self.assertEqual(game.phase, "hand_over")
        game.set_sit_out("p2", True)
        self.assertTrue(game.player_at(1).sitting_out)
        game.set_sit_out("p2", False)
        player = game.player_at(1)
        old_chips = player.chips
        player.chips = 0
        game.chip_total -= old_chips
        game.rebuy("p2")
        self.assertEqual(player.chips, 1000)
        self.assertTrue(game.check_chips())
        with self.assertRaises(GameError):
            game.rebuy("p1")


class TestThreePlayerPots(unittest.TestCase):
    def test_three_way_all_in_side_pots_different_winners(self):
        game = make_game(3, chips=[100, 300, 1000])
        order = parse_cards("KS QS AS KH QH AH 4C 2C 7D 9S 5D JC 6C 3H")
        game.start_hand(order)
        self.assertEqual((game.dealer_seat, game.sb_seat, game.bb_seat), (0, 1, 2))
        self.assertEqual(game.actor_seat, 0)
        game.act("p1", "allin")
        game.act("p2", "allin")
        game.act("p3", "call")
        self.assertEqual(game.phase, "hand_over")
        self.assertEqual(game.result["reason"], "showdown")
        # Main pot 300 to Alice (aces), side pot 400 to Bob (kings).
        self.assertEqual(game.player_at(0).chips, 300)
        self.assertEqual(game.player_at(1).chips, 400)
        self.assertEqual(game.player_at(2).chips, 700)
        self.assertEqual(sum(p.chips for p in game.seats), 1400)
        layers = game.result["pot_layers"]
        self.assertEqual({layer["label"] for layer in layers}, {"Main Pot", "Side Pot 1"})
        main = next(layer for layer in layers if layer["label"] == "Main Pot")
        side = next(layer for layer in layers if layer["label"] == "Side Pot 1")
        self.assertEqual(main["amount"], 300)
        self.assertEqual(side["amount"], 400)
        self.assertEqual(main["winners"][0]["seat"], 0)
        self.assertEqual(side["winners"][0]["seat"], 1)
        self.assertTrue(game.check_chips())
        self.assertEqual(game.pot_stack.size(), 2)

    def test_uncalled_excess_returned(self):
        game = make_game(3, chips=[1000, 100, 1000])
        order = parse_cards("QS AS KH QH AH KD 4C 2C 7D 9S 5D JC 6C 3H")
        game.start_hand(order)
        game.act("p1", "raise", 500)
        game.act("p2", "allin")
        game.act("p3", "fold")
        self.assertEqual(game.phase, "hand_over")
        # Alice raised 500, Bob could only match 100: 400 comes straight back.
        self.assertEqual(game.player_at(0).chips, 1110)
        self.assertEqual(game.player_at(1).chips, 0)
        self.assertEqual(game.player_at(2).chips, 990)
        self.assertTrue(any("Uncalled" in entry["label"]
                            for entry in game.action_stack.recent(50)))
        self.assertTrue(game.check_chips())

    def test_odd_chip_goes_first_left_of_dealer(self):
        game = make_game(3)
        order = parse_cards(
            "2H 2D 2C 3C 3S 3D 4C 10S JS QS 5C KS 6C AS"
        )
        game.start_hand(order)
        game.act("p1", "call")
        game.act("p2", "fold")
        game.act("p3", "check")
        while game.phase in ("flop", "turn", "river"):
            # Acting seat rotates, but both remaining players just check.
            game.act(game.player_at(game.actor_seat).id, "check")
        self.assertEqual(game.phase, "hand_over")
        self.assertEqual([c.code for c in game.community],
                         ["10S", "JS", "QS", "KS", "AS"])
        self.assertEqual(len(game.result["winners"]), 2)
        amounts = {w["seat"]: w["amount"] for w in game.result["winners"]}
        self.assertEqual(amounts, {2: 13, 0: 12})
        self.assertEqual(game.player_at(0).chips, 1002)
        self.assertEqual(game.player_at(1).chips, 995)
        self.assertEqual(game.player_at(2).chips, 1003)
        self.assertTrue(game.check_chips())

    def test_folded_player_cannot_win(self):
        game = make_game(3)
        game.start_hand(parse_cards("KS QS AS KH QH AH 4C 2C 7D 9S 5D JC 6C 3H"))
        # Alice (aces) folds; Bob's kings should beat Cara's queens.
        game.act("p1", "fold")
        game.act("p2", "call")
        game.act("p3", "check")
        while game.phase in ("flop", "turn", "river"):
            game.act(game.player_at(game.actor_seat).id, "check")
        winners = game.result["winners"]
        self.assertEqual(winners[0]["seat"], 1)
        self.assertEqual(game.player_at(0).won, 0)


class TestRandomSimulation(unittest.TestCase):
    """Play thousands of random legal hands and assert game invariants."""

    def random_hand(self, rng, seats):
        game = make_game(seats)
        settings = game.settings
        game.start_hand()
        actions = 0
        while game.phase in ("preflop", "flop", "turn", "river"):
            actions += 1
            self.assertLess(actions, 400, "hand appears stuck")
            actor = game.player_at(game.actor_seat)
            self.assertIsNotNone(actor)
            legal = game.legal_actions(actor)
            self.assertTrue(legal["is_turn"])
            options = ["fold", "allin"]
            if legal["check"]["allowed"]:
                options += ["check", "check", "check"]
            if legal["call"]["allowed"]:
                options += ["call", "call", "call"]
            if legal["wager"]["allowed"]:
                options += ["raise", "raise", "raise"]
            action = rng.choice(options)
            amount = None
            if action == "raise":
                low = legal["wager"]["min"]
                high = legal["wager"]["max"]
                amount = rng.choice([low, high, rng.randint(low, high)])
            try:
                game.act(actor.id, action, amount=amount)
            except (ActionError, GameError) as exc:
                self.fail(f"random legal action {action} {amount} rejected: {exc}")
        self.assertEqual(game.phase, "hand_over")
        self.assertTrue(game.check_chips(), "chips not conserved")
        self.assertEqual(sum(p.chips for p in game.seats), game.chip_total)
        all_cards = (
            game.deck.cards.to_list_top_first()
            + game.deck.burn.to_list_top_first()
            + game.community
            + [card for p in game.seats if p for card in p.cards]
        )
        self.assertEqual(len(all_cards), 52)
        self.assertEqual(len(set(all_cards)), 52, "duplicate card dealt")
        for p in game.seats:
            if p:
                self.assertGreaterEqual(p.chips, 0)
        return actions

    def test_thousands_of_random_hands(self):
        rng = random.Random(20261024)
        total_actions = 0
        hands = 2000
        for index in range(hands):
            seats = rng.randint(2, 6)
            total_actions += self.random_hand(rng, seats)
        self.assertGreater(total_actions, hands * 3)


class TestHandHistoryAndMultiHand(unittest.TestCase):
    def test_hand_history_last_first_and_chip_conservation(self):
        game = make_game(2)
        for _ in range(5):
            if game.phase in ("preflop", "flop", "turn", "river"):
                break
            if not game.start_hand():
                break
            while game.phase in ("preflop", "flop", "turn", "river"):
                game.act(game.player_at(game.actor_seat).id, "check"
                         if game.legal_actions(game.player_at(game.actor_seat))["check"]["allowed"]
                         else "call")
            self.assertTrue(game.check_chips())
            if game.player_at(0).chips < game.settings.big_blind:
                game.player_at(0).chips += 1000
                game.chip_total += 1000
            if game.player_at(1).chips < game.settings.big_blind:
                game.player_at(1).chips += 1000
                game.chip_total += 1000
            game._finalize_leavers()
        history = game.hand_history.top_first(10)
        self.assertGreaterEqual(len(history), 3)
        for earlier, later in zip(history, history[1:]):
            self.assertGreater(earlier["hand_no"], later["hand_no"])
        self.assertTrue(game.check_chips())


if __name__ == "__main__":
    unittest.main()
