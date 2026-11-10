"""A hand-written Stack (LIFO) data structure.

This is the star of the *Fundamentals of Data Structures* project.  PokerStack
uses this class instead of Python lists/deques for every place where last-in,
first-out behaviour is meaningful (deck, burn pile, action history, hand
history and side pots).

Every core operation below is O(1):

    push   O(1)   add an item on top
    pop    O(1)   remove and return the top item
    peek   O(1)   look at the top item without removing it
    is_empty / size / clear                O(1)
    to_list_top_first                      O(n) (only for display/tests)

The class deliberately uses a plain Python list *inside* the ADT.  Game code
never touches that list: it only gets a copy through ``to_list_top_first``.
"""

from __future__ import annotations

from typing import Any, Iterable, Iterator, Optional


class StackError(Exception):
    """Base class for all Stack errors."""


class StackUnderflowError(StackError):
    """Raised when pop() or peek() is called on an empty stack."""


class StackOverflowError(StackError):
    """Raised when push() would exceed a stack's optional max_size."""


class Stack:
    """A generic LIFO stack with an optional fixed capacity.

    >>> s = Stack()
    >>> s.push("A")
    >>> s.push("B")
    >>> s.peek()
    'B'
    >>> s.pop()
    'B'
    >>> s.size()
    1
    """

    def __init__(self, max_size: Optional[int] = None, items: Optional[Iterable[Any]] = None) -> None:
        if max_size is not None and max_size < 0:
            raise ValueError("max_size cannot be negative")
        self._items: list[Any] = []
        self._max_size = max_size
        if items:
            for item in items:
                self.push(item)

    # ------------------------------------------------------------------ core
    def push(self, item: Any) -> None:
        """Push ``item`` onto the top of the stack. O(1)."""
        if self._max_size is not None and len(self._items) >= self._max_size:
            raise StackOverflowError(
                f"Stack is full (max_size={self._max_size}); cannot push another item."
            )
        self._items.append(item)

    def pop(self) -> Any:
        """Remove and return the top item. O(1).

        Raises StackUnderflowError when the stack is empty.
        """
        if not self._items:
            raise StackUnderflowError("Cannot pop from an empty stack.")
        return self._items.pop()

    def peek(self) -> Any:
        """Return the top item without removing it. O(1).

        Raises StackUnderflowError when the stack is empty.
        """
        if not self._items:
            raise StackUnderflowError("Cannot peek at an empty stack.")
        return self._items[-1]

    def is_empty(self) -> bool:
        """True when the stack holds no items. O(1)."""
        return not self._items

    def size(self) -> int:
        """Number of items currently on the stack. O(1)."""
        return len(self._items)

    def clear(self) -> None:
        """Remove every item. O(1) (drops the internal list reference)."""
        self._items = []

    def to_list_top_first(self) -> list[Any]:
        """Return a shallow copy, top item first. O(n).

        The copy protects the ADT's internal storage from outside mutation.
        """
        return list(reversed(self._items))

    def to_list_bottom_first(self) -> list[Any]:
        """Return a shallow copy, bottom item first. O(n)."""
        return list(self._items)

    @property
    def max_size(self) -> Optional[int]:
        """The fixed capacity, or None for an unbounded stack."""
        return self._max_size

    def is_full(self) -> bool:
        """True when a max_size is set and has been reached. O(1)."""
        return self._max_size is not None and len(self._items) >= self._max_size

    # --------------------------------------------------------------- niceties
    def __len__(self) -> int:
        return len(self._items)

    def __bool__(self) -> bool:
        return bool(self._items)

    def __iter__(self) -> Iterator[Any]:
        """Iterate top-first (without removing anything)."""
        return iter(reversed(self._items))

    def __repr__(self) -> str:
        if not self._items:
            return "Stack([])"
        top = self._items[-1]
        return f"Stack(size={len(self._items)}, top={top!r})"
