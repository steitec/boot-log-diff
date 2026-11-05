import json
import re
import xml.etree.ElementTree as ET

import pytest

from boot_log_diff import BUILTIN_RULES, compare, parse_rules
from boot_log_diff.report import render_html, render_json, render_junit, render_text

GOLDEN = """\
U-Boot 2023.04
[    1.100000] mmc2: new HS400 Enhanced strobe MMC card at address 0001
[    1.204511] ata1: SATA link up 6.0 Gbps (SStatus 133 SControl 300)
[    1.300000] nvme nvme0: 8/0/0 default/read/poll queues
[    1.312003] Micrel KSZ9031 Gigabit PHY 30be0000.ethernet-1:07: attached PHY driver
[    1.402119] rtc-pcf85063 1-0051: registered as rtc0
[    1.511280] usb 1-1: new high-speed USB device number 2 using ci_hdrc
[    1.511900] usb 1-2: new high-speed USB device number 3 using ci_hdrc
[    1.600000] imx6q-pcie 33800000.pcie: Link up
[    1.650000] spi-nor spi0.0: w25q256 (32768 Kbytes)
[    1.702345] flexcan 308c0000.can: registering netdev can0
[    3.120345] fec 30be0000.ethernet eth0: Link is Up - 1Gbps/Full - flow control rx/tx
board login:
"""


def fault_ids(golden, dut, **kwargs):
    return [fault.rule.id for fault in compare(golden, dut, **kwargs).faults]


def without(fragment, text=GOLDEN):
    return "".join(line for line in text.splitlines(keepends=True) if fragment not in line)


@pytest.mark.parametrize(
    "fragment, rule_id",
    [
        ("mmc2: new", "mmc-card-missing"),
        ("SATA link up", "sata-link-missing"),
        ("nvme nvme0", "nvme-missing"),
        ("attached PHY driver", "eth-driver-missing"),
        ("Link is Up", "eth-link-missing"),
        ("usb 1-2", "usb-device-missing"),
        ("Link up", "pcie-link-missing"),
        ("registered as rtc0", "rtc-missing"),
        ("spi-nor", "spi-flash-missing"),
        ("flexcan", "can-missing"),
    ],
)
def test_builtin_rule_fires_when_the_line_is_gone(fragment, rule_id):
    assert fault_ids(GOLDEN, without(fragment)) == [rule_id]


def test_missing_fault_points_at_the_golden_line():
    fault = compare(GOLDEN, without("flexcan")).faults[0]
    assert [line.number for line in fault.lines] == [11]
    assert fault.log == "golden"


def test_same_log_has_no_faults():
    assert fault_ids(GOLDEN, GOLDEN) == []


def test_changed_value_is_not_a_missing_device():
    dut = GOLDEN.replace("Link is Up - 1Gbps/Full", "Link is Up - 100Mbps/Full")
    assert fault_ids(GOLDEN, dut) == []


def test_one_of_two_usb_devices_gone_counts():
    assert fault_ids(GOLDEN, without("usb 1-1")) == ["usb-device-missing"]


def test_moved_line_is_not_missing():
    lines = GOLDEN.splitlines(keepends=True)
    lines[9], lines[10] = lines[10], lines[9]
    assert fault_ids(GOLDEN, "".join(lines)) == []
    assert fault_ids(GOLDEN, "".join(lines), strict_order=True) == []


def test_line_also_missing_from_golden_does_not_fire():
    assert fault_ids(without("flexcan"), without("flexcan")) == []


def test_specific_fault_explains_the_missing_line():
    dut = GOLDEN.replace(
        "[    1.312003] Micrel KSZ9031 Gigabit PHY 30be0000.ethernet-1:07: attached PHY driver",
        "[    1.313120] fec 30be0000.ethernet eth0: Unable to connect to phy",
    )
    dut = without("Link is Up", dut)
    assert fault_ids(GOLDEN, dut) == ["eth-phy"]


def test_boot_stopping_reports_one_fault_not_every_driver():
    dut = "".join(GOLDEN.splitlines(keepends=True)[:3])
    faults = compare(GOLDEN, dut).faults
    assert [fault.rule.id for fault in faults] == ["boot-incomplete"]
    assert [line.number for line in faults[0].lines] == [4]


def test_boot_stopping_keeps_the_new_line_fault():
    dut = "".join(GOLDEN.splitlines(keepends=True)[:2]) + "[    2.0] ata1: COMRESET failed (errno=-16)\n"
    assert fault_ids(GOLDEN, dut) == ["sata-link", "boot-incomplete"]


def test_changed_last_line_is_not_a_stopped_boot():
    dut = GOLDEN.replace("board login:", "board2 login:")
    assert fault_ids(GOLDEN, dut) == []


def test_empty_dut_log_is_a_stopped_boot():
    assert fault_ids(GOLDEN, "") == ["boot-incomplete"]


def test_ignored_golden_line_does_not_fire():
    from boot_log_diff import Normalizer

    normalizer = Normalizer(ignore=[re.compile("flexcan")])
    assert fault_ids(GOLDEN, without("flexcan"), normalizer=normalizer) == []


def test_own_missing_rule_with_unless():
    rules = parse_rules(
        """
[[fault]]
id = "fpga-missing"
title = "FPGA did not load"
match = "missing"
pattern = 'flexcan'
unless = ["kernel-panic"]
diagnosis = "Check the FPGA."
"""
    )
    assert rules[0].match == "missing"
    assert rules[0].unless == ("kernel-panic",)
    assert fault_ids(GOLDEN, without("flexcan"), rules=rules) == ["fpga-missing"]


def test_own_rule_replaces_builtin_missing_rule_by_id():
    rules = parse_rules(
        """
[[fault]]
id = "can-missing"
title = "No CAN on this variant"
match = "missing"
pattern = 'flexcan'
severity = "warning"
diagnosis = "Expected."
"""
    )
    faults = compare(GOLDEN, without("flexcan"), rules=rules + list(BUILTIN_RULES)).faults
    assert [(f.rule.id, f.rule.severity) for f in faults] == [("can-missing", "warning")]


@pytest.mark.parametrize(
    "extra, message",
    [
        ("match = 'gone'\n", "match must be"),
        ("unless = ['a']\n", "unless"),
        ("match = 'missing'\nunless = 'a'\n", "unless"),
        ("match = 'unreached'\nunless = ['a']\n", "unless"),
    ],
)
def test_parse_errors(extra, message):
    text = f"[[fault]]\nid = 'x'\ntitle = 't'\npattern = 'p'\ndiagnosis = 'd'\n{extra}"
    with pytest.raises(ValueError, match=message):
        parse_rules(text, "rules.toml")


def test_reports_name_the_golden_log():
    result = compare(GOLDEN, without("flexcan"))
    text = render_text(result, "g", "d")
    assert "(can-missing), golden line 11" in text

    data = json.loads(render_json(result, "g", "d"))
    fault = data["faults"][0]
    assert (fault["log"], fault["lines"][0]["line"]) == ("golden", 11)

    assert "golden line 11:" in render_html(result, "g", "d")

    root = ET.fromstring(render_junit(result, "g", "d"))
    failure = [case for case in root.iter("testcase") if case.get("name") == "can-missing"][0].find("failure")
    assert "golden line 11:" in failure.text


def test_new_line_fault_still_names_the_dut_log():
    dut = GOLDEN.replace("board login:", "Kernel panic - not syncing\nboard login:")
    result = compare(GOLDEN, dut)
    assert "(kernel-panic), dut line 13" in render_text(result, "g", "d")
    assert json.loads(render_json(result, "g", "d"))["faults"][0]["log"] == "dut"
