"""Text and JSON output of a comparison result."""

from __future__ import annotations

import json

from .compare import Line, Result

_RED = "\x1b[31m"
_GREEN = "\x1b[32m"
_BOLD_RED = "\x1b[1;31m"
_CYAN = "\x1b[36m"
_DIM = "\x1b[2m"
_RESET = "\x1b[0m"


def render_text(result: Result, golden_name: str, dut_name: str, color: bool = False) -> str:
    def paint(code: str, text: str) -> str:
        return f"{code}{text}{_RESET}" if color else text

    out = [f"golden: {golden_name}", f"dut:    {dut_name}"]

    if result.facts:
        out += ["", "Facts that differ:"]
        width = max(len(fact.name) for fact in result.facts)
        for fact in result.facts:
            golden = fact.golden if fact.golden is not None else "(not found)"
            dut = fact.dut if fact.dut is not None else "(not found)"
            out.append(f"  {fact.name:<{width}}  {golden}  ->  {paint(_BOLD_RED, dut)}")

    for hunk in result.hunks:
        out += ["", paint(_CYAN, f"@@ golden line {hunk.golden_start}, dut line {hunk.dut_start} @@")]
        out += [paint(_RED, f"-  {line.text}") for line in hunk.removed]
        for line in hunk.added:
            out.append(paint(_BOLD_RED, f"+! {line.text}") if line.error else paint(_GREEN, f"+  {line.text}"))

    s = result.summary()
    out.append("")
    if not result.has_deviations:
        text = "no deviations"
        if s["moved"]:
            text += f" ({s['moved']} moved)"
        out.append(text)
    else:
        out.append(
            f"{s['facts_changed']} facts changed, {s['missing']} missing, {s['new']} new "
            f"({s['new_errors']} look like errors), {s['moved']} moved"
        )
    if result.moved:
        out.append(paint(_DIM, "moved lines are drivers probing in another order; --strict-order shows them"))
    return "\n".join(out) + "\n"


def _line(line: Line) -> dict[str, object]:
    return {"line": line.number, "text": line.text, "error": line.error}


def render_json(result: Result, golden_name: str, dut_name: str) -> str:
    data = {
        "golden": golden_name,
        "dut": dut_name,
        "deviations": result.has_deviations,
        "summary": result.summary(),
        "facts": [{"name": f.name, "golden": f.golden, "dut": f.dut} for f in result.facts],
        "hunks": [
            {
                "golden_start": hunk.golden_start,
                "dut_start": hunk.dut_start,
                "removed": [_line(line) for line in hunk.removed],
                "added": [_line(line) for line in hunk.added],
            }
            for hunk in result.hunks
        ],
        "moved": [{"golden": _line(g), "dut": _line(d)} for g, d in result.moved],
    }
    return json.dumps(data, indent=2) + "\n"
