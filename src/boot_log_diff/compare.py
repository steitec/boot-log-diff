"""Comparison of a golden boot log with the log of a board under test."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .normalize import Normalizer, clean

# Words that make a new line worth a second look.
ERROR_WORDS = re.compile(
    r"\b(?:error|errors|fail|failed|failure|fault|unable|cannot|can't|timeout|"
    r"timed out|panic|oops|warning|not found|no such|bad|corrupt\w*|call trace|bug:)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Fact:
    """A value worth comparing on its own, taken from the first group of `pattern`."""

    name: str
    pattern: re.Pattern[str]


def _fact(name: str, pattern: str) -> Fact:
    return Fact(name, re.compile(pattern))


BUILTIN_FACTS: tuple[Fact, ...] = (
    _fact("model", r"(?:^|\] )(?:Machine model|Model):\s*(.+)$"),
    _fact("u-boot", r"^U-Boot (\d{4}\.\d{2}\S*)"),
    _fact("dram", r"^DRAM:\s*(.+)$"),
    _fact("kernel", r"Linux version (\S+)"),
    _fact("memory", r"Memory: \d+K/(\d+K) available"),
    _fact("cpus", r"Brought up .*?(\d+) CPUs?\b"),
)


@dataclass(frozen=True)
class Line:
    number: int
    text: str
    normalized: str

    @property
    def error(self) -> bool:
        return bool(ERROR_WORDS.search(self.text))


@dataclass
class Hunk:
    """A run of golden lines (`removed`) replaced by DUT lines (`added`)."""

    golden_start: int
    dut_start: int
    removed: list[Line] = field(default_factory=list)
    added: list[Line] = field(default_factory=list)


@dataclass(frozen=True)
class FactDiff:
    name: str
    golden: str | None
    dut: str | None


@dataclass
class Result:
    facts: list[FactDiff]
    hunks: list[Hunk]
    moved: list[tuple[Line, Line]]

    @property
    def has_deviations(self) -> bool:
        return bool(self.facts or self.hunks)

    def summary(self) -> dict[str, int]:
        added = [line for hunk in self.hunks for line in hunk.added]
        return {
            "missing": sum(len(hunk.removed) for hunk in self.hunks),
            "new": len(added),
            "new_errors": sum(line.error for line in added),
            "moved": len(self.moved),
            "facts_changed": len(self.facts),
        }


def _lines(text: str, normalizer: Normalizer) -> tuple[list[str], list[Line]]:
    cleaned, compared = [], []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = clean(raw)
        if not line.strip():
            continue
        cleaned.append(line)
        normalized = normalizer(line)
        if normalized is not None:
            compared.append(Line(number, line, normalized))
    return cleaned, compared


def _facts(lines: list[str], facts: Iterable[Fact]) -> dict[str, str]:
    found = {}
    for fact in facts:
        for line in lines:
            match = fact.pattern.search(line)
            if match:
                found[fact.name] = match.group(1).strip()
                break
    return found


def _start(lines: list[Line], index: int) -> int:
    if index < len(lines):
        return lines[index].number
    return lines[-1].number + 1 if lines else 1


def _take_moved(hunks: list[Hunk]) -> list[tuple[Line, Line]]:
    """Pair lines that only changed position and take them out of the hunks."""
    removed = Counter(line.normalized for hunk in hunks for line in hunk.removed)
    added = Counter(line.normalized for hunk in hunks for line in hunk.added)
    candidates = {
        text: [line for hunk in hunks for line in hunk.added if line.normalized == text]
        for text in removed & added
    }
    moved = []
    for hunk in hunks:
        for line in hunk.removed:
            if candidates.get(line.normalized):
                moved.append((line, candidates[line.normalized].pop(0)))
    taken = {id(line) for pair in moved for line in pair}
    for hunk in hunks:
        hunk.removed = [line for line in hunk.removed if id(line) not in taken]
        hunk.added = [line for line in hunk.added if id(line) not in taken]
    hunks[:] = [hunk for hunk in hunks if hunk.removed or hunk.added]
    return moved


def compare(
    golden: str,
    dut: str,
    normalizer: Normalizer | None = None,
    facts: Iterable[Fact] = BUILTIN_FACTS,
    strict_order: bool = False,
) -> Result:
    """Compare two boot logs given as text.

    Lines that only moved are reported in `Result.moved` and do not count as
    a deviation, because drivers probing in parallel do not keep their order.
    With `strict_order` they show up as missing and new lines instead.
    """
    normalizer = normalizer or Normalizer()
    facts = list(facts)
    golden_all, golden_lines = _lines(golden, normalizer)
    dut_all, dut_lines = _lines(dut, normalizer)

    golden_facts = _facts(golden_all, facts)
    dut_facts = _facts(dut_all, facts)
    fact_diffs = [
        FactDiff(fact.name, golden_facts.get(fact.name), dut_facts.get(fact.name))
        for fact in facts
        if golden_facts.get(fact.name) != dut_facts.get(fact.name)
    ]

    matcher = SequenceMatcher(
        None,
        [line.normalized for line in golden_lines],
        [line.normalized for line in dut_lines],
        autojunk=False,
    )
    hunks = [
        Hunk(_start(golden_lines, i1), _start(dut_lines, j1), golden_lines[i1:i2], dut_lines[j1:j2])
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        if tag != "equal"
    ]
    moved = [] if strict_order else _take_moved(hunks)
    return Result(fact_diffs, hunks, moved)
