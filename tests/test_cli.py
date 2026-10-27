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
