"""Command line interface: boot-log-diff GOLDEN DUT."""

from __future__ import annotations

import argparse
import os
import re
import sys

from . import __version__
from .compare import BUILTIN_FACTS, Fact, compare
from .normalize import BUILTIN_MASK_NAMES, Mask, Normalizer
from .report import render_json, render_text

EPILOG = """\
exit status: 0 no deviations, 1 deviations found, 2 usage or input error

built-in masks: """ + ", ".join(BUILTIN_MASK_NAMES) + """
built-in facts: """ + ", ".join(fact.name for fact in BUILTIN_FACTS)


class _UsageError(Exception):
    pass


def _regex(option: str, pattern: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise _UsageError(f"{option} {pattern!r}: {exc}") from None


def _fact(value: str) -> tuple[str, str]:
    name, sep, pattern = value.partition("=")
    if not sep or not name or not pattern:
        raise argparse.ArgumentTypeError(f"expected NAME=REGEX, got {value!r}")
    return name, pattern


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="boot-log-diff",
        description="Compare the serial boot log of a board under test with a "
        "known-good golden log. Timestamps, addresses, dates and other values "
        "that change from boot to boot are masked, so only real deviations remain.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("golden", help="boot log of a known-good board")
    parser.add_argument("dut", help="boot log of the board under test ('-' reads stdin)")
    parser.add_argument(
        "--mask", action="append", default=[], metavar="REGEX",
        help="also mask matches of REGEX, e.g. serial numbers or host names (repeatable)",
    )
    parser.add_argument(
        "--ignore", action="append", default=[], metavar="REGEX",
        help="leave out lines matching REGEX (repeatable)",
    )
    parser.add_argument(
        "--no-mask", action="append", default=[], metavar="NAME", choices=BUILTIN_MASK_NAMES,
        help="switch off a built-in mask (repeatable)",
    )
    parser.add_argument(
        "--fact", action="append", default=[], type=_fact, metavar="NAME=REGEX",
        help="compare the first group of REGEX as a named fact (repeatable)",
    )
    parser.add_argument(
        "--strict-order", action="store_true",
        help="report lines that only moved as missing and new",
    )
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    parser.add_argument(
        "--color", choices=["auto", "always", "never"], default="auto",
        help="colour the text output (default: auto)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _read(path: str) -> str:
    if path == "-":
        data = sys.stdin.buffer.read()
    else:
        try:
            with open(path, "rb") as file:
                data = file.read()
        except OSError as exc:
            raise _UsageError(f"{path}: {exc.strerror}") from None
    return data.decode("utf-8", errors="replace")


def _use_color(choice: str) -> bool:
    if choice != "auto":
        return choice == "always"
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        normalizer = Normalizer(
            extra=[Mask(f"mask{i}", _regex("--mask", p), "<MASK>") for i, p in enumerate(args.mask)],
            ignore=[_regex("--ignore", p) for p in args.ignore],
            disabled=args.no_mask,
        )
        facts = list(BUILTIN_FACTS) + [
            Fact(name, _regex("--fact", pattern)) for name, pattern in args.fact
        ]
        golden = _read(args.golden)
        dut = _read(args.dut)
    except _UsageError as exc:
        print(f"boot-log-diff: error: {exc}", file=sys.stderr)
        return 2

    result = compare(golden, dut, normalizer, facts, strict_order=args.strict_order)
    dut_name = "<stdin>" if args.dut == "-" else args.dut
    if args.json:
        sys.stdout.write(render_json(result, args.golden, dut_name))
    else:
        sys.stdout.write(render_text(result, args.golden, dut_name, _use_color(args.color)))
    return 1 if result.has_deviations else 0
