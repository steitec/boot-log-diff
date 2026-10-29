"""Output of a comparison result: text, JSON, JUnit XML and HTML."""

from __future__ import annotations

import html
import json
import re
import textwrap
import xml.etree.ElementTree as ET

from .compare import Hunk, Line, Result
from .faults import Fault

_RED = "\x1b[31m"
_GREEN = "\x1b[32m"
_BOLD_RED = "\x1b[1;31m"
_CYAN = "\x1b[36m"
_YELLOW = "\x1b[33m"
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

    if result.faults:
        out += ["", "Known faults:"]
        for fault in result.faults:
            label = paint(_BOLD_RED if fault.rule.severity == "error" else _YELLOW, f"[{fault.rule.severity}]")
            out.append(f"  {label} {fault.rule.title} ({fault.rule.id}), {_dut_lines(fault)}")
            out += textwrap.wrap(fault.rule.diagnosis, 76, initial_indent="      ", subsequent_indent="      ")

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
            + (f", {s['faults']} known faults" if s["faults"] else "")
        )
    if result.moved:
        out.append(paint(_DIM, "moved lines are drivers probing in another order; --strict-order shows them"))
    return "\n".join(out) + "\n"


def _dut_lines(fault: Fault) -> str:
    numbers = [str(line.number) for line in fault.lines]
    return ("dut line " if len(numbers) == 1 else "dut lines ") + ", ".join(numbers)


def _line(line: Line) -> dict[str, object]:
    return {"line": line.number, "text": line.text, "error": line.error}


def render_json(result: Result, golden_name: str, dut_name: str) -> str:
    data = {
        "golden": golden_name,
        "dut": dut_name,
        "deviations": result.has_deviations,
        "summary": result.summary(),
        "facts": [{"name": f.name, "golden": f.golden, "dut": f.dut} for f in result.facts],
        "faults": [
            {
                "id": fault.rule.id,
                "title": fault.rule.title,
                "severity": fault.rule.severity,
                "diagnosis": fault.rule.diagnosis,
                "lines": [_line(line) for line in fault.lines],
            }
            for fault in result.faults
        ],
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


def _hunk_text(hunk: Hunk) -> list[str]:
    out = [f"@@ golden line {hunk.golden_start}, dut line {hunk.dut_start} @@"]
    out += [f"-  {line.text}" for line in hunk.removed]
    out += [f"{'+!' if line.error else '+ '} {line.text}" for line in hunk.added]
    return out


# Characters XML 1.0 does not allow, which a serial capture may contain.
_XML_INVALID = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def _xml(text: str) -> str:
    return _XML_INVALID.sub("\ufffd", text)


def render_junit(result: Result, golden_name: str, dut_name: str) -> str:
    """JUnit XML: one test case per fact, one for the log lines, one per fault rule."""
    suite = ET.Element("testsuite", name=_xml(f"boot-log-diff {dut_name}"))
    properties = ET.SubElement(suite, "properties")
    ET.SubElement(properties, "property", name="golden", value=_xml(golden_name))
    ET.SubElement(properties, "property", name="dut", value=_xml(dut_name))
    failures = 0

    def case(classname: str, name: str, message: str | None = None, kind: str = "", body: str = "") -> None:
        nonlocal failures
        element = ET.SubElement(suite, "testcase", classname=f"boot-log-diff.{classname}", name=_xml(name))
        if message is not None:
            failures += 1
            failure = ET.SubElement(element, "failure", message=_xml(message), type=kind)
            failure.text = _xml(body)

    changed = {fact.name: fact for fact in result.facts}
    for name in result.fact_names:
        fact = changed.get(name)
        if fact is None:
            case("facts", name)
        else:
            golden = fact.golden if fact.golden is not None else "(not found)"
            dut = fact.dut if fact.dut is not None else "(not found)"
            case("facts", name, f"{golden} -> {dut}", "fact", f"golden: {golden}\ndut:    {dut}")

    s = result.summary()
    if result.hunks:
        body = "\n\n".join("\n".join(_hunk_text(hunk)) for hunk in result.hunks)
        case("lines", "log lines", f"{s['missing']} missing, {s['new']} new", "lines", body)
    else:
        case("lines", "log lines")

    found = {fault.rule.id: fault for fault in result.faults}
    for rule in result.rules:
        fault = found.get(rule.id)
        if fault is None:
            case("faults", rule.id)
        else:
            lines = "\n".join(f"dut line {line.number}: {line.text}" for line in fault.lines)
            case("faults", rule.id, rule.title, rule.severity, f"{rule.diagnosis}\n\n{lines}")

    suite.set("tests", str(len(suite.findall("testcase"))))
    suite.set("failures", str(failures))
    suite.set("errors", "0")
    suite.set("skipped", "0")
    ET.indent(suite)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(suite, encoding="unicode") + "\n"


_HTML_STYLE = """
:root { color-scheme: light dark; --bg: #fff; --fg: #1f2328; --muted: #656d76; --line: #d0d7de;
  --card: #f6f8fa; --red: #cf222e; --red-bg: #ffebe9; --green: #1a7f37; --green-bg: #dafbe1;
  --amber: #9a6700; --amber-bg: #fff8c5; --cyan: #0969da; }
@media (prefers-color-scheme: dark) { :root { --bg: #0d1117; --fg: #e6edf3; --muted: #8d96a0;
  --line: #30363d; --card: #161b22; --red: #ff7b72; --red-bg: #3c1618; --green: #3fb950;
  --green-bg: #12261e; --amber: #d29922; --amber-bg: #2e2410; --cyan: #58a6ff; } }
* { box-sizing: border-box; }
body { margin: 0 auto; max-width: 1100px; padding: 24px 16px 48px; background: var(--bg);
  color: var(--fg); font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
h1 { font-size: 1.5rem; margin: 0 0 4px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
h2 { font-size: 1.1rem; margin: 32px 0 8px; }
.verdict { font-size: .85rem; padding: 2px 10px; border-radius: 999px; font-weight: 600; }
.pass { background: var(--green-bg); color: var(--green); }
.fail { background: var(--red-bg); color: var(--red); }
.files { color: var(--muted); margin: 0; font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: .85rem; overflow-wrap: anywhere; }
.summary { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0 0; padding: 0; list-style: none; }
.summary li { background: var(--card); border: 1px solid var(--line); border-radius: 6px; padding: 6px 12px; }
.summary b { font-size: 1.1rem; margin-right: 4px; }
.fault { border: 1px solid var(--line); border-left: 4px solid var(--red); border-radius: 6px;
  padding: 10px 14px; margin: 8px 0; background: var(--card); }
.fault.warning { border-left-color: var(--amber); }
.fault h3 { margin: 0; font-size: 1rem; }
.fault .id, .muted { color: var(--muted); font-weight: normal; font-size: .85rem; }
.fault p { margin: 6px 0; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
td.dut { color: var(--red); font-weight: 600; }
pre { margin: 0; font: .82rem/1.45 ui-monospace, SFMono-Regular, Consolas, monospace; white-space: pre-wrap;
  overflow-wrap: anywhere; }
.hunk { border: 1px solid var(--line); border-radius: 6px; margin: 10px 0; overflow: hidden; }
.hunk .head { background: var(--card); color: var(--cyan); padding: 4px 10px; }
.hunk pre div { padding: 0 10px; }
.del { background: var(--red-bg); }
.add { background: var(--green-bg); }
.err { background: var(--red-bg); color: var(--red); font-weight: 600; }
.lines { margin: 6px 0 0; }
details summary { cursor: pointer; color: var(--muted); margin-top: 24px; }
footer { margin-top: 40px; color: var(--muted); font-size: .8rem; }
a { color: var(--cyan); }
"""


def render_html(result: Result, golden_name: str, dut_name: str, version: str = "") -> str:
    """A self-contained HTML page (no scripts, no external files)."""
    e = html.escape
    s = result.summary()
    ok = not result.has_deviations
    out = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>Boot log check: {e(dut_name)}</title>",
        f"<style>{_HTML_STYLE}</style></head><body>",
        f'<h1>Boot log check <span class="verdict {"pass" if ok else "fail"}">'
        f'{"no deviations" if ok else "deviations found"}</span></h1>',
        f'<p class="files">golden: {e(golden_name)}<br>dut:&nbsp;&nbsp;&nbsp; {e(dut_name)}</p>',
        '<ul class="summary">',
        f"<li><b>{s['faults']}</b>known faults</li>",
        f"<li><b>{s['facts_changed']}</b>facts changed</li>",
        f"<li><b>{s['missing']}</b>missing lines</li>",
        f"<li><b>{s['new']}</b>new lines ({s['new_errors']} look like errors)</li>",
        f"<li><b>{s['moved']}</b>moved</li>",
        "</ul>",
    ]

    if result.faults:
        out.append("<h2>Known faults</h2>")
        for fault in result.faults:
            rule = fault.rule
            lines = "".join(f"<div>{line.number}: {e(line.text)}</div>" for line in fault.lines)
            out.append(
                f'<div class="fault {rule.severity}"><h3>{e(rule.title)} '
                f'<span class="id">{e(rule.id)} · {rule.severity}</span></h3>'
                f"<p>{e(rule.diagnosis)}</p><pre class=\"lines\">{lines}</pre></div>"
            )

    if result.facts:
        out.append("<h2>Facts that differ</h2><table><tr><th>Fact</th><th>Golden</th><th>DUT</th></tr>")
        for fact in result.facts:
            golden = e(fact.golden) if fact.golden is not None else '<span class="muted">(not found)</span>'
            dut = e(fact.dut) if fact.dut is not None else "(not found)"
            out.append(f'<tr><td>{e(fact.name)}</td><td>{golden}</td><td class="dut">{dut}</td></tr>')
        out.append("</table>")

    if result.hunks:
        out.append("<h2>Lines that differ</h2>")
        for hunk in result.hunks:
            rows = [f'<div class="del">-  {e(line.text)}</div>' for line in hunk.removed]
            rows += [
                f'<div class="err">+! {e(line.text)}</div>' if line.error else f'<div class="add">+  {e(line.text)}</div>'
                for line in hunk.added
            ]
            out.append(
                f'<div class="hunk"><pre><div class="head">@@ golden line {hunk.golden_start}, '
                f'dut line {hunk.dut_start} @@</div>{"".join(rows)}</pre></div>'
            )

    if result.moved:
        rows = "".join(
            f"<div>golden {g.number} → dut {d.number}: {e(d.text)}</div>" for g, d in result.moved
        )
        out.append(
            f"<details><summary>{len(result.moved)} {'line' if len(result.moved) == 1 else 'lines'} "
            f"only moved (drivers probing in another order)</summary><pre class=\"lines\">{rows}</pre></details>"
        )

    footer = "boot-log-diff" + (f" {e(version)}" if version else "")
    out.append(f'<footer>Generated by <a href="https://github.com/steitec/boot-log-diff">{footer}</a></footer>')
    out.append("</body></html>")
    return "\n".join(out) + "\n"
