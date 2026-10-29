"""Compare the boot log of a board under test with a known-good golden log."""

from .compare import BUILTIN_FACTS, Fact, FactDiff, Hunk, Line, Result, compare
from .faults import BUILTIN_RULES, Fault, Rule, load_rules, parse_rules
from .normalize import BUILTIN_MASKS, Mask, Normalizer

__version__ = "0.2.0"

__all__ = [
    "BUILTIN_FACTS",
    "BUILTIN_MASKS",
    "BUILTIN_RULES",
    "Fact",
    "Fault",
    "FactDiff",
    "Hunk",
    "Line",
    "Mask",
    "Normalizer",
    "Result",
    "Rule",
    "compare",
    "load_rules",
    "parse_rules",
]
