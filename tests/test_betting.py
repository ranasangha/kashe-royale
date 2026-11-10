import unittest

from pokerstack.betting import ActionError, minimum_bet_target, validate_wager


class TestBettingRules(unittest.TestCase):
    def test_minimum_opening_bet(self):
        wager = validate_wager(
            current_bet=0, min_raise=10, big_blind=10,
            player_bet=0, chips=1000, amount=10,
        )
        self.assertTrue(wager.full_raise)
        self.assertEqual(wager.delta, 10)
        with self.assertRaises(ActionError):
            validate_wager(
                current_bet=0, min_raise=10, big_blind=10,
                player_bet=0, chips=1000, amount=9,
            )

    def test_short_all_in_bet_is_allowed(self):
        wager = validate_wager(
            current_bet=0, min_raise=10, big_blind=10,
            player_bet=0, chips=6, amount=6,
        )
        self.assertFalse(wager.full_raise)
        self.assertTrue(wager.is_all_in)

    def test_minimum_raise(self):
        # 100 outstanding, last raise 50 => must raise to at least 150.
        wager = validate_wager(
            current_bet=100, min_raise=50, big_blind=10,
            player_bet=0, chips=1000, amount=150,
        )
        self.assertTrue(wager.full_raise)
        self.assertEqual(wager.delta, 150)
        with self.assertRaises(ActionError):
            validate_wager(
                current_bet=100, min_raise=50, big_blind=10,
                player_bet=0, chips=1000, amount=149,
            )

    def test_short_all_in_raise_allowed(self):
        wager = validate_wager(
            current_bet=100, min_raise=50, big_blind=10,
            player_bet=0, chips=130, amount=130,
        )
        self.assertFalse(wager.full_raise)
        self.assertTrue(wager.is_all_in)

    def test_short_all_in_does_not_reopen_for_prior_actor(self):
        with self.assertRaises(ActionError):
            validate_wager(
                current_bet=130, min_raise=50, big_blind=10,
                player_bet=100, chips=1000, amount=300,
                short_call_only=True,
            )

    def test_cannot_wager_more_than_stack(self):
        with self.assertRaises(ActionError):
            validate_wager(
                current_bet=100, min_raise=50, big_blind=10,
                player_bet=0, chips=100, amount=250,
            )

    def test_raise_must_exceed_current_bet(self):
        with self.assertRaises(ActionError):
            validate_wager(
                current_bet=100, min_raise=50, big_blind=10,
                player_bet=100, chips=500, amount=100,
            )

    def test_no_chips(self):
        with self.assertRaises(ActionError):
            validate_wager(
                current_bet=100, min_raise=50, big_blind=10,
                player_bet=100, chips=0, amount=200,
            )

    def test_minimum_target_helpers(self):
        self.assertEqual(minimum_bet_target(
            current_bet=0, min_raise=10, big_blind=10, player_bet=0), 10)
        self.assertEqual(minimum_bet_target(
            current_bet=100, min_raise=50, big_blind=10, player_bet=0), 150)


if __name__ == "__main__":
    unittest.main()
