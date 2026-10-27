"""Compare the boot log of a board under test with a known-good golden log."""

from .compare import BUILTIN_FACTS, Fact, FactDiff, Hunk, Line, Result, compare
from .normalize import BUILTIN_MASKS, Mask, Normalizer

__version__ = "0.1.0"

__all__ = [
    "BUILTIN_FACTS",
    "BUILTIN_MASKS",
    "Fact",
    "FactDiff",
    "Hunk",
    "Line",
    "Mask",
    "Normalizer",
    "Result",
    "compare",
]
