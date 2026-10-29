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
_FIELDS = {"id", "title", "pattern", "diagnosis", "severity"}


@dataclass(frozen=True)
class Rule:
    """A known fault: lines matching `pattern` get `title` and `diagnosis`."""

    id: str
    title: str
    pattern: re.Pattern[str]
    diagnosis: str
    severity: str = "error"


@dataclass
class Fault:
    """A rule that matched, with the DUT lines it matched."""

    rule: Rule
    lines: list[Line] = field(default_factory=list)


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
        try:
            pattern = re.compile(entry["pattern"], re.IGNORECASE)
        except re.error as exc:
            raise ValueError(f"{where} ({entry['id']}): pattern: {exc}") from None
        rules.append(
            Rule(entry["id"], entry["title"], pattern, " ".join(entry["diagnosis"].split()), severity)
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
    """Match each line against the rules; a line counts for the first rule only.

    Of several rules with the same id only the first is used, so own rules
    placed before the built-in ones replace them. Faults are returned in the
    order they first show up in the log.
    """
    rules = unique_rules(rules)
    faults = {rule.id: Fault(rule) for rule in rules}
    for line in lines:
        for rule in rules:
            if rule.pattern.search(line.text):
                faults[rule.id].lines.append(line)
                break
    return sorted((fault for fault in faults.values() if fault.lines), key=lambda f: f.lines[0].number)
