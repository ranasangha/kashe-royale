import unittest

from pokerstack.cards import Card, parse_cards
from pokerstack.deck import Deck, DeckEmptyError
from pokerstack.stack import StackUnderflowError


class TestDeck(unittest.TestCase):
    def test_full_deck_has_52_unique_cards(self):
        deck = Deck()
        self.assertEqual(deck.remaining, 52)
        cards = deck.cards.to_list_top_first()
        self.assertEqual(len(cards), 52)
        self.assertEqual(len(set(cards)), 52)
        self.assertTrue(all(isinstance(c, Card) for c in cards))

    def test_deal_pops_top_and_reduces_size(self):
        deck = Deck(shuffle=False)
        top = deck.peek_top()
        self.assertEqual(deck.deal(), top)
        self.assertEqual(deck.remaining, 51)

    def test_burn_pushes_onto_burn_stack(self):
        deck = Deck()
        top = deck.peek_top()
        burned = deck.burn_one()
        self.assertEqual(burned, top)
        self.assertEqual(deck.burn_count, 1)
        self.assertEqual(deck.burn.peek(), burned)
        self.assertEqual(deck.remaining, 51)

    def test_rigged_deal_order(self):
        deck = Deck()
        order = parse_cards("AS KH 10D 2C")
        deck.rig(order)
        dealt = [deck.deal() for _ in range(4)]
        self.assertEqual(dealt, order)
        self.assertEqual(len(set(deck.cards.to_list_top_first()) | set(dealt)), 52)

    def test_rig_rejects_duplicates(self):
        deck = Deck()
        with self.assertRaises(ValueError):
            deck.rig(parse_cards("AS AS"))

    def test_empty_deck_raises(self):
        deck = Deck()
        for _ in range(52):
            deck.deal()
        with self.assertRaises(DeckEmptyError):
            deck.deal()
        with self.assertRaises(StackUnderflowError):
            deck.peek_top()

    def test_shuffle_changes_order(self):
        first = Deck().cards.to_list_top_first()
        second = Deck().cards.to_list_top_first()
        self.assertNotEqual(first, second)

    def test_deepcopy_preserves_next_cards(self):
        import copy
        deck = Deck()
        clone = copy.deepcopy(deck)
        self.assertEqual(deck.cards.to_list_top_first(), clone.cards.to_list_top_first())
        self.assertEqual(deck.deal(), clone.deal())

    def test_no_duplicates_after_many_deals(self):
        deck = Deck()
        dealt = [deck.deal() for _ in range(20)]
        burned = deck.burn_one()
        self.assertEqual(len(set(dealt + [burned] + deck.cards.to_list_top_first())), 52)


if __name__ == "__main__":
    unittest.main()
