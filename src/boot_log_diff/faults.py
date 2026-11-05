"""Known faults: rules that turn typical boot log messages into a diagnosis."""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib.resources import files
from typing import TYPE_CHECKING

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

if TYPE_CHECKING:
    from .compare import Line

SEVERITIES = ("error", "warning")
MATCHES = ("new", "missing", "unreached")
_FIELDS = {"id", "title", "pattern", "diagnosis", "severity", "match", "unless"}


@dataclass(frozen=True)
class Rule:
    """A known fault: lines matching `pattern` get `title` and `diagnosis`.

    `match` says which lines the pattern is applied to: "new" lines of the DUT
    log, golden lines "missing" from the DUT log, or golden lines "unreached"
    because the DUT log stopped early. A "missing" rule stays silent if a fault
    listed in `unless` was found, because that fault already explains the line.
    """

    id: str
    title: str
    pattern: re.Pattern[str]
    diagnosis: str
    severity: str = "error"
    match: str = "new"
    unless: tuple[str, ...] = ()


@dataclass
class Fault:
    """A rule that matched, with the DUT lines it matched."""

    rule: Rule
    lines: list[Line] = field(default_factory=list)

    @property
    def log(self) -> str:
        """The log the line numbers refer to: "dut" or "golden"."""
        return "dut" if self.rule.match == "new" else "golden"


def parse_rules(text: str, source: str = "<rules>") -> list[Rule]:
    """Read rules from TOML text with one [[fault]] table per rule."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{source}: {exc}") from None
    entries = data.get("fault", [])
    if not isinstance(entries, list) or set(data) - {"fault"}:
        raise ValueError(f"{source}: expected only [[fault]] tables")
    rules = []
    for number, entry in enumerate(entries, start=1):
        where = f"{source}: fault #{number}"
        unknown = set(entry) - _FIELDS
        if unknown:
            raise ValueError(f"{where}: unknown field(s) {', '.join(sorted(unknown))}")
        missing = [name for name in ("id", "title", "pattern", "diagnosis") if not entry.get(name)]
        if missing:
            raise ValueError(f"{where}: missing {', '.join(missing)}")
        severity = entry.get("severity", "error")
        if severity not in SEVERITIES:
            raise ValueError(f"{where} ({entry['id']}): severity must be error or warning")
        match = entry.get("match", "new")
        if match not in MATCHES:
            raise ValueError(f"{where} ({entry['id']}): match must be new, missing or unreached")
        unless = entry.get("unless", [])
        if not isinstance(unless, list) or not all(isinstance(item, str) for item in unless):
            raise ValueError(f"{where} ({entry['id']}): unless must be a list of fault ids")
        if unless and match != "missing":
            raise ValueError(f"{where} ({entry['id']}): unless only works with match = \"missing\"")
        try:
            pattern = re.compile(entry["pattern"], re.IGNORECASE)
        except re.error as exc:
            raise ValueError(f"{where} ({entry['id']}): pattern: {exc}") from None
        rules.append(
            Rule(
                entry["id"],
                entry["title"],
                pattern,
                " ".join(entry["diagnosis"].split()),
                severity,
                match,
                tuple(unless),
            )
        )
    return rules


def load_rules(path: str) -> list[Rule]:
    """Read rules from a TOML file."""
    try:
        with open(path, "rb") as file:
            text = file.read().decode("utf-8")
    except OSError as exc:
        raise ValueError(f"{path}: {exc.strerror}") from None
    return parse_rules(text, path)


BUILTIN_RULES: tuple[Rule, ...] = tuple(
    parse_rules(files(__package__).joinpath("faults.toml").read_text("utf-8"), "faults.toml")
)


def unique_rules(rules: Iterable[Rule]) -> list[Rule]:
    """The rules in order, without later rules that repeat an id."""
    seen: dict[str, Rule] = {}
    for rule in rules:
        seen.setdefault(rule.id, rule)
    return list(seen.values())


def find_faults(lines: Iterable[Line], rules: Iterable[Rule]) -> list[Fault]:
    """Match each new DUT line against the "new" rules; a line counts for the first only.

    Of several rules with the same id only the first is used, so own rules
    placed before the built-in ones replace them. Faults are returned in the
    order they first show up in the log.
    """
    rules = [rule for rule in unique_rules(rules) if rule.match == "new"]
    faults = {rule.id: Fault(rule) for rule in rules}
    for line in lines:
        for rule in rules:
            if rule.pattern.search(line.text):
                faults[rule.id].lines.append(line)
                break
    return sorted((fault for fault in faults.values() if fault.lines), key=lambda f: f.lines[0].number)


def _count(lines: list[Line], rule: Rule) -> int:
    return sum(1 for line in lines if rule.pattern.search(line.text))


def find_missing(
    removed: Iterable[Line],
    golden: Iterable[Line],
    dut: Iterable[Line],
    rules: Iterable[Rule],
    found: Iterable[str] = (),
) -> list[Fault]:
    """Match golden lines gone from the DUT log against the "missing" rules.

    A rule fires only if the DUT log has fewer matching lines than the golden
    log. A line that merely changed a value (a link at a lower speed) still
    matches, so it does not count as a device that went away. Rules are checked
    in order and see the faults of earlier rules through `unless`.
    """
    removed, golden, dut = list(removed), list(golden), list(dut)
    found = set(found)
    taken: set[int] = set()
    faults = []
    for rule in unique_rules(rules):
        if rule.match != "missing" or found.intersection(rule.unless):
            continue
        if _count(golden, rule) <= _count(dut, rule):
            continue
        lines = [line for line in removed if id(line) not in taken and rule.pattern.search(line.text)]
        if lines:
            taken.update(id(line) for line in lines)
            faults.append(Fault(rule, lines))
            found.add(rule.id)
    return faults


def find_unreached(lines: Iterable[Line], rules: Iterable[Rule]) -> list[Fault]:
    """Match golden lines the DUT log never got to; each rule keeps the first one."""
    lines = list(lines)
    faults = []
    for rule in unique_rules(rules):
        if rule.match == "unreached":
            first = next((line for line in lines if rule.pattern.search(line.text)), None)
            if first is not None:
                faults.append(Fault(rule, [first]))
    return faults
