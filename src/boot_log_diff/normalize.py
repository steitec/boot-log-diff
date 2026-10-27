"""Line cleanup and masking of values that change from boot to boot."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True)
class Mask:
    """Replaces every match of `pattern` with `replacement`."""

    name: str
    pattern: re.Pattern[str]
    replacement: str


def _mask(name: str, pattern: str, replacement: str) -> Mask:
    return Mask(name, re.compile(pattern, re.IGNORECASE), replacement)


# Values that differ between two healthy boots of the same board. The order
# matters: a date must be masked before its digits can look like anything else.
BUILTIN_MASKS: tuple[Mask, ...] = (
    _mask(
        "datetime",
        r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
        r"(?: UTC)?(?: \(\d+\))?",
        "<DATETIME>",
    ),
    _mask("timestamp", r"\[\s*\d+\.\d+\]", "[<TS>]"),
    _mask("uuid", r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "<UUID>"),
    _mask("mac", r"\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\b", "<MAC>"),
    _mask("hex", r"\b0x[0-9a-f]+\b|\b[0-9a-f]{12,}\b", "<HEX>"),
    _mask("ip", r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "<IP>"),
    _mask("duration", r"\b\d+(?:\.\d+)?\s?(?:ms|us|µs|ns|s)\b", "<DURATION>"),
    _mask("rate", r"\b\d+(?:\.\d+)?\s?[KMG]i?B/s\b", "<RATE>"),
    _mask("temp", r"(?<![\w.])-?\d+(?:\.\d+)?\s?°?C\b", "<TEMP>"),
    _mask("bogomips", r"\b\d+\.\d+ BogoMIPS\b", "<BOGOMIPS>"),
)

BUILTIN_MASK_NAMES = tuple(mask.name for mask in BUILTIN_MASKS)


def clean(line: str) -> str:
    """Remove terminal colour codes, carriage returns and trailing blanks."""
    return _ANSI.sub("", line).replace("\r", "").rstrip()


class Normalizer:
    """Turns a cleaned log line into the form that is compared.

    Built-in masks can be switched off by name, extra masks run after them.
    A line matching one of the `ignore` patterns is dropped (returns None).
    """

    def __init__(
        self,
        extra: Iterable[Mask] = (),
        ignore: Iterable[re.Pattern[str]] = (),
        disabled: Iterable[str] = (),
    ) -> None:
        disabled = set(disabled)
        unknown = disabled - set(BUILTIN_MASK_NAMES)
        if unknown:
            raise ValueError(f"unknown mask name(s): {', '.join(sorted(unknown))}")
        self.masks = [m for m in BUILTIN_MASKS if m.name not in disabled] + list(extra)
        self.ignore = list(ignore)

    def __call__(self, line: str) -> str | None:
        if any(pattern.search(line) for pattern in self.ignore):
            return None
        for mask in self.masks:
            line = mask.pattern.sub(mask.replacement, line)
        return _SPACES.sub(" ", line).strip()
