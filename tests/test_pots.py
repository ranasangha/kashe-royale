import unittest

from pokerstack.pots import PotLayer, PotStack, build_pots, split_pot


class TestPots(unittest.TestCase):
    def test_simple_single_pot(self):
        layers = build_pots({0: 100, 1: 100, 2: 100})
        self.assertEqual(len(layers), 1)
        self.assertEqual(layers[0].amount, 300)
        self.assertEqual(layers[0].eligible, (0, 1, 2))
        self.assertEqual(layers[0].label, "Main Pot")

    def test_three_players_different_all_ins(self):
        # A all-in 100, B all-in 300, C covers both.
        layers = build_pots({0: 100, 1: 300, 2: 300})
        self.assertEqual([layer.amount for layer in layers], [300, 400])
        self.assertEqual(layers[0].eligible, (0, 1, 2))
        self.assertEqual(layers[1].eligible, (1, 2))
        self.assertEqual(layers[1].label, "Side Pot 1")
        self.assertEqual(sum(layer.amount for layer in layers), 700)

    def test_folded_player_money_stays_in_pots(self):
        layers = build_pots({0: 100, 1: 100, 2: 500}, folded={2})
        # 2 folded; 500 includes 200 dead chips above the contested 100 level.
        self.assertEqual(sum(layer.amount for layer in layers), 700)
        self.assertEqual(layers[0].eligible, (0, 1))
        self.assertTrue(all(2 not in layer.eligible for layer in layers))

    def test_multi_level_side_pots(self):
        layers = build_pots({0: 50, 1: 150, 2: 300, 3: 300})
        self.assertEqual([layer.amount for layer in layers], [200, 300, 300])
        self.assertEqual(layers[0].eligible, (0, 1, 2, 3))
        self.assertEqual(layers[1].eligible, (1, 2, 3))
        self.assertEqual(layers[2].eligible, (2, 3))

    def test_pot_stack_resolves_top_first(self):
        stack = PotStack()
        stack.push_layer(PotLayer(300, (0, 1, 2), "Main Pot"))
        stack.push_layer(PotLayer(400, (1, 2), "Side Pot 1"))
        self.assertEqual(stack.total(), 700)
        self.assertEqual(stack.top_layer().label, "Side Pot 1")
        self.assertEqual([layer.label for layer in stack.layers_top_first()],
                         ["Side Pot 1", "Main Pot"])
        self.assertEqual([layer.label for layer in stack.layers_bottom_first()],
                         ["Main Pot", "Side Pot 1"])
        self.assertEqual(stack.size(), 2)

    def test_split_even(self):
        self.assertEqual(split_pot(100, [2, 0]), {2: 50, 0: 50})

    def test_split_odd_chip_goes_to_first_clockwise(self):
        self.assertEqual(split_pot(101, [2, 0]), {2: 51, 0: 50})
        self.assertEqual(split_pot(25, [2, 0]), {2: 13, 0: 12})

    def test_split_three_ways(self):
        shares = split_pot(100, [1, 2, 0])
        self.assertEqual(sum(shares.values()), 100)
        self.assertEqual(shares, {1: 34, 2: 33, 0: 33})

    def test_empty(self):
        self.assertEqual(build_pots({}), [])
        self.assertEqual(split_pot(10, []), {})


if __name__ == "__main__":
    unittest.main()
