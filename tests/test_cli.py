import io
import json
from pathlib import Path

import pytest

from boot_log_diff.cli import main

EXAMPLES = Path(__file__).parent.parent / "examples"
GOLDEN = str(EXAMPLES / "golden.log")
FAULTY = str(EXAMPLES / "faulty.log")


def run(capsys, *args):
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def test_same_log_exits_zero(capsys):
    code, out, _ = run(capsys, GOLDEN, GOLDEN, "--color", "never")
    assert code == 0
    assert "no deviations" in out


def test_example_finds_the_real_faults(capsys):
    code, out, _ = run(
        capsys, GOLDEN, FAULTY, "--color", "never", "--mask", r"epc8m-[0-9a-f]+"
    )
    assert code == 1
    assert "dram" in out and "2 GiB" in out and "1 GiB" in out
    assert "-  [    1.312003] Micrel KSZ9031" in out
    assert "+! [    1.313120] fec 30be0000.ethernet eth0: Unable to connect to phy" in out
    assert "+! [    4.611290] mmc1: Timeout waiting for hardware interrupt." in out
    # Noise that must not show up as a deviation:
    assert "bytes read in" not in out
    assert "setting system clock" not in out
    assert "login:" not in out
    assert "1 moved" in out


def test_without_hostname_mask_the_hostname_differs(capsys):
    _, out, _ = run(capsys, GOLDEN, FAULTY, "--color", "never")
    assert "login:" in out


def test_json_output(capsys):
    code, out, _ = run(capsys, GOLDEN, FAULTY, "--json", "--mask", r"epc8m-[0-9a-f]+")
    assert code == 1
    data = json.loads(out)
    assert data["summary"]["new_errors"] == 3
    assert {"name": "dram", "golden": "2 GiB", "dut": "1 GiB"} in data["facts"]
    added = [line for hunk in data["hunks"] for line in hunk["added"]]
    assert any(line["error"] and "Unable to connect" in line["text"] for line in added)


def test_dut_from_stdin(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(Path(GOLDEN).read_bytes())))
    code, _, _ = run(capsys, GOLDEN, "-")
    assert code == 0


def test_ignore_and_no_mask(capsys, tmp_path):
    golden = tmp_path / "g.log"
    dut = tmp_path / "d.log"
    golden.write_text("CPU at 38C\nrandom: crng init done\n")
    dut.write_text("CPU at 44C\n")
    assert run(capsys, str(golden), str(dut), "--ignore", "crng")[0] == 0
    assert run(capsys, str(golden), str(dut), "--ignore", "crng", "--no-mask", "temp")[0] == 1


def test_custom_fact(capsys, tmp_path):
    golden = tmp_path / "g.log"
    dut = tmp_path / "d.log"
    golden.write_text("FPGA bitstream v1.4 loaded\n")
    dut.write_text("FPGA bitstream v1.3 loaded\n")
    code, out, _ = run(
        capsys, str(golden), str(dut), "--color", "never", "--fact", r"fpga=bitstream v(\S+)"
    )
    assert code == 1
    assert "fpga" in out and "1.4" in out and "1.3" in out


def test_invalid_regex_exits_two(capsys):
    code, _, err = run(capsys, GOLDEN, GOLDEN, "--ignore", "(")
    assert code == 2
    assert "--ignore" in err


def test_missing_file_exits_two(capsys):
    code, _, err = run(capsys, GOLDEN, "does-not-exist.log")
    assert code == 2
    assert "does-not-exist.log" in err


def test_invalid_fact_exits_two(capsys):
    with pytest.raises(SystemExit) as exc:
        main([GOLDEN, GOLDEN, "--fact", "no-equals-sign"])
    assert exc.value.code == 2


def test_example_shows_known_faults(capsys):
    code, out, _ = run(capsys, GOLDEN, FAULTY, "--color", "never", "--mask", r"epc8m-[0-9a-f]+")
    assert code == 1
    assert "Known faults:" in out
    assert "[error] Ethernet PHY not found (eth-phy), dut line 50" in out
    assert "[error] eMMC/SD card does not respond (timeout) (mmc-timeout), dut lines 62, 63" in out
    assert out.index("eth-phy") < out.index("mmc-timeout")
    assert "2 known faults" in out


def test_no_builtin_rules(capsys):
    _, out, _ = run(capsys, GOLDEN, FAULTY, "--color", "never", "--no-builtin-rules")
    assert "Known faults" not in out


def test_own_rules_file(capsys, tmp_path):
    rules = tmp_path / "rules.toml"
    rules.write_text(
        "[[fault]]\nid = 'sd-slot'\ntitle = 'SD slot dead'\n"
        "pattern = 'mmc1: error -110'\ndiagnosis = 'Replace the SD connector J12.'\n"
    )
    _, out, _ = run(capsys, GOLDEN, FAULTY, "--color", "never", "--rules", str(rules), "--json")
    faults = {f["id"]: f for f in json.loads(out)["faults"]}
    assert [line["line"] for line in faults["sd-slot"]["lines"]] == [63]
    assert [line["line"] for line in faults["mmc-timeout"]["lines"]] == [62]
    assert faults["sd-slot"]["diagnosis"] == "Replace the SD connector J12."


def test_bad_rules_file_exits_two(capsys, tmp_path):
    rules = tmp_path / "rules.toml"
    rules.write_text("[[fault]]\nid = 'x'\n")
    code, _, err = run(capsys, GOLDEN, FAULTY, "--rules", str(rules))
    assert code == 2
    assert "--rules" in err and "missing" in err
    code, _, err = run(capsys, GOLDEN, FAULTY, "--rules", str(tmp_path / "nope.toml"))
    assert code == 2
    assert "nope.toml" in err


def test_junit_report(capsys, tmp_path):
    import xml.etree.ElementTree as ET

    from boot_log_diff import BUILTIN_RULES

    report = tmp_path / "junit.xml"
    code, _, _ = run(capsys, GOLDEN, FAULTY, "--junit", str(report), "--mask", r"epc8m-[0-9a-f]+")
    assert code == 1
    suite = ET.parse(report).getroot()
    cases = {(c.get("classname"), c.get("name")): c for c in suite.iter("testcase")}
    assert int(suite.get("tests")) == len(cases) == 6 + 1 + len(BUILTIN_RULES)
    failed = sorted(name for (_, name), case in cases.items() if case.find("failure") is not None)
    assert failed == ["dram", "eth-phy", "log lines", "memory", "mmc-timeout"]
    assert suite.get("failures") == "5"
    phy = cases[("boot-log-diff.faults", "eth-phy")].find("failure")
    assert phy.get("message") == "Ethernet PHY not found"
    assert "dut line 50: " in phy.text and "MDIO" in phy.text


def test_junit_report_passes_on_same_log(capsys, tmp_path):
    import xml.etree.ElementTree as ET

    report = tmp_path / "junit.xml"
    assert run(capsys, GOLDEN, GOLDEN, "--junit", str(report))[0] == 0
    suite = ET.parse(report).getroot()
    assert suite.get("failures") == "0"


def test_junit_survives_control_characters(capsys, tmp_path):
    import xml.etree.ElementTree as ET

    golden = tmp_path / "g.log"
    dut = tmp_path / "d.log"
    golden.write_text("boot ok\n")
    dut.write_bytes(b"boot \x00\x07 failed\n")
    report = tmp_path / "junit.xml"
    assert run(capsys, str(golden), str(dut), "--junit", str(report))[0] == 1
    ET.parse(report)


def test_html_report(capsys, tmp_path):
    report = tmp_path / "report.html"
    code, _, _ = run(capsys, GOLDEN, FAULTY, "--html", str(report), "--mask", r"epc8m-[0-9a-f]+")
    assert code == 1
    page = report.read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>")
    assert "deviations found" in page
    assert "Ethernet PHY not found" in page and "Check the PHY supply" in page
    assert '<td class="dut">1 GiB</td>' in page
    assert "<script" not in page


def test_html_escapes_log_text(capsys, tmp_path):
    golden = tmp_path / "g.log"
    dut = tmp_path / "d.log"
    golden.write_text("ok\n")
    dut.write_text("<script>alert(1)</script> failed\n")
    report = tmp_path / "report.html"
    run(capsys, str(golden), str(dut), "--html", str(report))
    page = report.read_text(encoding="utf-8")
    assert "<script>" not in page
    assert "&lt;script&gt;" in page


def test_report_write_error_exits_two(capsys, tmp_path):
    code, _, err = run(capsys, GOLDEN, GOLDEN, "--html", str(tmp_path / "missing-dir" / "r.html"))
    assert code == 2
    assert "r.html" in err
