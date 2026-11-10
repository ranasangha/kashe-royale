import unittest

from pokerstack.stack import Stack, StackOverflowError, StackUnderflowError


class TestStack(unittest.TestCase):
    def test_lifo_order(self):
        stack = Stack()
        for value in ("A", "B", "C"):
            stack.push(value)
        self.assertEqual(stack.size(), 3)
        self.assertEqual(stack.peek(), "C")
        self.assertEqual(stack.pop(), "C")
        self.assertEqual(stack.pop(), "B")
        self.assertEqual(stack.pop(), "A")
        self.assertTrue(stack.is_empty())

    def test_underflow_pop_and_peek(self):
        stack = Stack()
        with self.assertRaises(StackUnderflowError):
            stack.pop()
        with self.assertRaises(StackUnderflowError):
            stack.peek()

    def test_overflow(self):
        stack = Stack(max_size=2)
        stack.push(1)
        stack.push(2)
        self.assertTrue(stack.is_full())
        with self.assertRaises(StackOverflowError):
            stack.push(3)

    def test_clear_and_size(self):
        stack = Stack(items=[1, 2, 3])
        self.assertEqual(stack.size(), 3)
        stack.clear()
        self.assertTrue(stack.is_empty())
        stack.push(9)
        self.assertEqual(stack.size(), 1)

    def test_to_list_top_first_is_a_copy(self):
        stack = Stack()
        for value in (1, 2, 3):
            stack.push(value)
        listed = stack.to_list_top_first()
        self.assertEqual(listed, [3, 2, 1])
        listed.append(99)
        self.assertEqual(stack.size(), 3)
        self.assertEqual(stack.to_list_bottom_first(), [1, 2, 3])

    def test_iteration_is_top_first(self):
        stack = Stack(items=[1, 2, 3])
        self.assertEqual(list(stack), [3, 2, 1])

    def test_negative_max_size_rejected(self):
        with self.assertRaises(ValueError):
            Stack(max_size=-1)

    def test_bool(self):
        stack = Stack()
        self.assertFalse(stack)
        stack.push(0)
        self.assertTrue(stack)


if __name__ == "__main__":
    unittest.main()
