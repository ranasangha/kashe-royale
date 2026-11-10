import unittest

from pokerstack.cards import parse_cards
from pokerstack.evaluator import (
    FLUSH,
    FOUR_OF_A_KIND,
    FULL_HOUSE,
    HIGH_CARD,
    ONE_PAIR,
    STRAIGHT,
    STRAIGHT_FLUSH,
    THREE_OF_A_KIND,
    TWO_PAIR,
    compare,
    evaluate,
    evaluate_five,
)


class TestEvaluator(unittest.TestCase):
    def test_royal_flush(self):
        hand = evaluate(parse_cards("AS KS QS JS 10S 2H 3D"))
        self.assertEqual(hand.category, STRAIGHT_FLUSH)
        self.assertEqual(hand.name, "Royal Flush")
        self.assertEqual(hand.key, (STRAIGHT_FLUSH, 14))
        self.assertEqual({c.code for c in hand.cards}, {"AS", "KS", "QS", "JS", "10S"})

    def test_straight_flush_nine_high(self):
        hand = evaluate(parse_cards("9H 8H 7H 6H 5H AD KC"))
        self.assertEqual(hand.category, STRAIGHT_FLUSH)
        self.assertEqual(hand.name, "Straight Flush, Nine High")

    def test_four_of_a_kind_with_kicker(self):
        hand = evaluate(parse_cards("7S 7H 7D 7C AS 2D 3C"))
        self.assertEqual(hand.category, FOUR_OF_A_KIND)
        self.assertEqual(hand.tiebreak, (7, 14))

    def test_full_house_beats_flush(self):
        full = evaluate(parse_cards("9S 9H 9D 4C 4S 2D 3H"))
        flush = evaluate(parse_cards("AS KS 9S 6S 3S 2D 4H"))
        self.assertEqual(full.category, FULL_HOUSE)
        self.assertEqual(flush.category, FLUSH)
        self.assertEqual(compare(full, flush), 1)

    def test_wheel_is_five_high_straight(self):
        hand = evaluate(parse_cards("AS 2H 3D 4C 5S 9H 10D"))
        self.assertEqual(hand.category, STRAIGHT)
        self.assertEqual(hand.key, (STRAIGHT, 5))
        self.assertIn("Wheel", hand.name)

    def test_qka23_is_not_a_straight(self):
        hand = evaluate(parse_cards("QS KH AD 2C 3D 7H 8S"))
        self.assertEqual(hand.category, HIGH_CARD)
        self.assertNotEqual(hand.category, STRAIGHT)

    def test_two_pair_with_kicker(self):
        hand = evaluate(parse_cards("AS AH 9D 9C KS 2D 3H"))
        self.assertEqual(hand.category, TWO_PAIR)
        self.assertEqual(hand.tiebreak, (14, 9, 13))

    def test_trips_kickers(self):
        hand = evaluate(parse_cards("5S 5H 5D AS KC 2D 3H"))
        self.assertEqual(hand.category, THREE_OF_A_KIND)
        self.assertEqual(hand.tiebreak, (5, 14, 13))

    def test_one_pair_kicker_battle(self):
        ace_king = evaluate(parse_cards("AS AH KD 8C 5S 3D 2H"))
        ace_queen = evaluate(parse_cards("AD AC QS 8H 5D 3C 2S"))
        self.assertEqual(ace_king.category, ONE_PAIR)
        self.assertGreater(compare(ace_king, ace_queen), 0)
        self.assertLess(compare(ace_queen, ace_king), 0)

    def test_identical_hands_tie_and_suits_do_not_matter(self):
        board = parse_cards("AS KH QD JC 9S")
        left = evaluate(board + parse_cards("2C 3D"))
        right = evaluate(board + parse_cards("2D 3C"))
        self.assertEqual(compare(left, right), 0)

    def test_best_five_of_seven(self):
        hand = evaluate(parse_cards("AS KS QS JS 10S 2H 3D"))
        self.assertEqual(len(hand.cards), 5)
        self.assertEqual(evaluate_five(parse_cards("AS KS QS JS 10S")).name, "Royal Flush")

    def test_board_plays(self):
        board = parse_cards("10S JS QS KS AS")
        hand = evaluate(board + parse_cards("2C 3D"))
        self.assertEqual(hand.name, "Royal Flush")

    def test_high_card_ordering(self):
        hand = evaluate(parse_cards("AS KD 9C 7H 4S 2D 3C"))
        self.assertEqual(hand.category, HIGH_CARD)
        self.assertEqual(hand.tiebreak[:3], (14, 13, 9))

    def test_fewer_than_five_rejected(self):
        with self.assertRaises(ValueError):
            evaluate(parse_cards("AS KS QS JS"))


if __name__ == "__main__":
    unittest.main()
