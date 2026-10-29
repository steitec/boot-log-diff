import re

from boot_log_diff import Fact, Normalizer, compare


GOLDEN = """\
U-Boot 2023.04 (Oct 02 2026)
DRAM:  2 GiB
[    0.010924] smp: Brought up 1 node, 4 CPUs
[    1.102331] mmc2: SDHCI controller
[    1.104412] mmc1: SDHCI controller
[    1.312003] Micrel KSZ9031 Gigabit PHY: attached PHY driver
[    1.402119] rtc-pcf85063 1-0051: registered as rtc0
login:
"""


def test_identical_after_normalization_has_no_deviations():
    dut = GOLDEN.replace("0.010924", "0.011002").replace("1.402119", "1.399000")
    result = compare(GOLDEN, dut)
    assert result.hunks == []
    assert result.facts == []
    assert not result.has_deviations


def test_blank_lines_are_ignored():
    result = compare(GOLDEN, GOLDEN.replace("\n", "\n\n"))
    assert not result.has_deviations


def test_missing_and_new_lines_with_line_numbers():
    dut = GOLDEN.replace(
        "[    1.312003] Micrel KSZ9031 Gigabit PHY: attached PHY driver",
        "[    1.313120] fec eth0: Unable to connect to phy",
    )
    result = compare(GOLDEN, dut)
    assert len(result.hunks) == 1
    hunk = result.hunks[0]
    assert [(line.number, line.text) for line in hunk.removed] == [
        (6, "[    1.312003] Micrel KSZ9031 Gigabit PHY: attached PHY driver")
    ]
    assert [(line.number, line.error) for line in hunk.added] == [(6, True)]
    assert result.summary() == {
        "missing": 1, "new": 1, "new_errors": 1, "moved": 0, "facts_changed": 0, "faults": 1,
    }
    assert result.has_deviations


def test_reordered_lines_are_reported_as_moved_not_as_deviation():
    lines = GOLDEN.splitlines()
    lines[3], lines[4] = lines[4], lines[3]
    result = compare(GOLDEN, "\n".join(lines))
    assert result.hunks == []
    assert len(result.moved) == 1
    assert not result.has_deviations


def test_strict_order_reports_reordered_lines():
    lines = GOLDEN.splitlines()
    lines[3], lines[4] = lines[4], lines[3]
    result = compare(GOLDEN, "\n".join(lines), strict_order=True)
    assert result.moved == []
    assert result.has_deviations


def test_duplicate_lines_only_move_as_often_as_they_occur():
    golden = "x\nx\na\nb\n"
    dut = "a\nb\nx\n"
    result = compare(golden, dut)
    assert len(result.moved) == 1
    assert [line.text for h in result.hunks for line in h.removed] == ["x"]
    assert [line.text for h in result.hunks for line in h.added] == []


def test_builtin_facts_changed():
    dut = GOLDEN.replace("DRAM:  2 GiB", "DRAM:  1 GiB").replace("4 CPUs", "2 CPUs")
    result = compare(GOLDEN, dut)
    assert [(f.name, f.golden, f.dut) for f in result.facts] == [
        ("dram", "2 GiB", "1 GiB"),
        ("cpus", "4", "2"),
    ]


def test_fact_missing_on_one_side():
    dut = GOLDEN.replace("DRAM:  2 GiB\n", "")
    result = compare(GOLDEN, dut)
    assert [(f.name, f.golden, f.dut) for f in result.facts] == [("dram", "2 GiB", None)]


def test_custom_fact_and_normalizer():
    golden = "board serial 0001 rev B\n"
    dut = "board serial 0002 rev C\n"
    result = compare(
        golden,
        dut,
        normalizer=Normalizer(ignore=[re.compile("serial")]),
        facts=[Fact("revision", re.compile(r"rev (\w+)"))],
    )
    assert result.hunks == []
    assert [(f.name, f.golden, f.dut) for f in result.facts] == [("revision", "B", "C")]
