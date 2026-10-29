import re

import pytest

from boot_log_diff import BUILTIN_RULES, Rule, compare, parse_rules
from boot_log_diff.compare import Line
from boot_log_diff.faults import find_faults

GOLDEN = """\
U-Boot 2023.04
DRAM:  2 GiB
[    1.312003] Micrel KSZ9031 Gigabit PHY: attached PHY driver
[    1.402119] rtc-pcf85063 1-0051: registered as rtc0
login:
"""


def ids(text):
    lines = [Line(n, t, t) for n, t in enumerate(text.splitlines(), start=1)]
    return [fault.rule.id for fault in find_faults(lines, BUILTIN_RULES)]


# One typical message per built-in rule, as real boards print them.
@pytest.mark.parametrize(
    "rule_id, line",
    [
        ("ddr-training", "DDRINFO: ddrphy training failed"),
        ("ddr-training", "LPDDR4 calibration failed for channel 1"),
        ("mmc-timeout", "[    4.611290] mmc1: Timeout waiting for hardware interrupt."),
        ("mmc-timeout", "[    4.612001] mmc1: error -110 whilst initialising SD card"),
        ("mmc-crc", "[    2.100000] mmc2: Got data interrupt 0x00200000 even though no data operation was in progress. CRC error"),
        ("mmc-io-error", "[    9.100000] blk_update_request: I/O error, dev mmcblk2, sector 34816"),
        ("eth-phy", "[    1.313120] fec 30be0000.ethernet eth0: Unable to connect to phy"),
        ("eth-phy", "Could not get PHY for ethernet@30be0000: addr 7"),
        ("eth-no-link", "[   12.000000] fec 30be0000.ethernet eth0: Link is Down"),
        ("usb-enumeration", "[    2.000000] usb 1-1: device descriptor read/64, error -71"),
        ("usb-enumeration", "[    3.000000] usb 1-1: device not accepting address 3, error -71"),
        ("usb-overcurrent", "[    2.500000] usb usb1-port1: over-current condition"),
        ("i2c-nack", "[    1.500000] i2c i2c-1: i2c read error -121"),
        ("i2c-nack", "[    1.600000] pca953x: probe of 2-0020 failed with error -5"),
        ("spi-flash", "[    1.000000] spi-nor spi0.0: unrecognized JEDEC id bytes: ff ff ff ff ff ff"),
        ("spi-flash", "SF: Unsupported flash IDs: manuf 00, jedec 0000, ext_jedec 0000"),
        ("nand", "[    1.000000] nand: No NAND device found"),
        ("pcie-link", "[    2.000000] imx6q-pcie 33800000.pcie: Phy link never came up"),
        ("rootfs-mount", "[    2.000000] VFS: Unable to mount root fs on unknown-block(179,2)"),
        ("fs-corruption", "[    5.000000] EXT4-fs error (device mmcblk2p2): ext4_lookup:1700: inode #2: comm init: deleted inode referenced: 12"),
        ("bad-image", "Bad Linux ARM64 Image magic!"),
        ("bad-image", "   Verifying Checksum ... Bad Data CRC"),
        ("env-default", "*** Warning - bad CRC, using default environment"),
        ("kernel-panic", "[    3.000000] Kernel panic - not syncing: Attempted to kill init!"),
        ("kernel-panic", "[    3.000000] Unable to handle kernel NULL pointer dereference at virtual address 0000000000000008"),
        ("watchdog-reset", "Reset cause: WDOG"),
        ("power", "[    2.000000] reg-fixed-voltage regulator-usdhc2: Failed to enable supply"),
        ("power", "[   60.000000] hwmon hwmon1: Undervoltage detected!"),
        ("thermal", "[   99.000000] thermal thermal_zone0: critical temperature reached (105 C), shutting down"),
        ("memory-ecc", "[   50.000000] EDAC MC0: 1 CE single-bit error on mc#0csrow#0"),
        ("firmware-missing", "[    6.000000] brcmfmac mmc0:0001:1: Direct firmware load for brcm/brcmfmac43455-sdio.bin failed with error -2"),
        ("rcu-stall", "[   30.000000] rcu: INFO: rcu_preempt detected stalls on CPUs/tasks:"),
    ],
)
def test_builtin_rule_matches_typical_message(rule_id, line):
    assert ids(line) == [rule_id]


# Lines from healthy boots that must not look like a known fault.
@pytest.mark.parametrize(
    "line",
    [
        "[    1.312003] Micrel KSZ9031 Gigabit PHY 30be0000.ethernet-1:07: attached PHY driver",
        "[    3.120345] fec 30be0000.ethernet eth0: Link is Up - 1Gbps/Full - flow control rx/tx",
        "[    1.216002] mmc2: new HS400 Enhanced strobe MMC card at address 0001",
        "[    0.900000] imx2-wdt 30280000.watchdog: timeout 60 sec (nowayout=0)",
        "[    0.500000] EDAC DEVICE0: Giving out device to module edac controller",
        "Reset cause: POR",
        "DDRINFO:ddrphy calibration done",
        "Loading Environment from MMC... OK",
        "[    1.849662] EXT4-fs (mmcblk2p2): mounted filesystem with ordered data mode.",
        "[    2.000000] thermal_sys: Registered thermal governor 'step_wise'",
    ],
)
def test_builtin_rules_ignore_healthy_lines(line):
    assert ids(line) == []


def test_builtin_rule_ids_are_unique():
    rule_ids = [rule.id for rule in BUILTIN_RULES]
    assert len(rule_ids) == len(set(rule_ids))


def test_only_new_lines_count():
    golden = GOLDEN + "*** Warning - bad CRC, using default environment\n"
    dut = golden.replace(
        "[    1.312003] Micrel KSZ9031 Gigabit PHY: attached PHY driver",
        "[    1.313120] fec eth0: Unable to connect to phy",
    )
    result = compare(golden, dut)
    assert [(f.rule.id, [line.number for line in f.lines]) for f in result.faults] == [("eth-phy", [3])]
    assert result.summary()["faults"] == 1


def test_faults_in_log_order_and_one_rule_per_line():
    dut = GOLDEN.replace("login:", "mmc1: error -110 whilst initialising SD card\nlogin:").replace(
        "DRAM:  2 GiB", "DRAM:  2 GiB\nDDRINFO: training failed"
    )
    result = compare(GOLDEN, dut)
    assert [f.rule.id for f in result.faults] == ["ddr-training", "mmc-timeout"]


def test_rules_can_be_switched_off():
    dut = GOLDEN.replace("login:", "Kernel panic - not syncing\nlogin:")
    assert compare(GOLDEN, dut, rules=()).faults == []


def test_parse_rules_and_override_by_id():
    rules = parse_rules(
        """
[[fault]]
id = "eth-phy"
title = "Our PHY is not fitted on variant B"
pattern = 'unable to connect to phy'
diagnosis = "Expected on variant B."
severity = "warning"

[[fault]]
id = "fpga"
title = "FPGA not configured"
pattern = 'fpga.*done pin low'
diagnosis = \"\"\"
Check the FPGA
configuration flash.\"\"\"
"""
    )
    assert [r.id for r in rules] == ["eth-phy", "fpga"]
    assert rules[1].diagnosis == "Check the FPGA configuration flash."
    assert rules[1].pattern.flags & re.IGNORECASE
    dut = GOLDEN.replace(
        "[    1.312003] Micrel KSZ9031 Gigabit PHY: attached PHY driver",
        "fec eth0: Unable to connect to phy\nFPGA: DONE pin low",
    )
    result = compare(GOLDEN, dut, rules=rules + list(BUILTIN_RULES))
    assert [(f.rule.id, f.rule.severity) for f in result.faults] == [("eth-phy", "warning"), ("fpga", "error")]
    assert len(result.rules) == len(BUILTIN_RULES) + 1


@pytest.mark.parametrize(
    "text, message",
    [
        ("[[fault]]\nid = 'x'\ntitle = 't'\npattern = '('\ndiagnosis = 'd'\n", "pattern"),
        ("[[fault]]\nid = 'x'\ntitle = 't'\ndiagnosis = 'd'\n", "missing pattern"),
        ("[[fault]]\nid = 'x'\ntitle = 't'\npattern = 'p'\ndiagnosis = 'd'\nlevel = 1\n", "unknown field"),
        ("[[fault]]\nid = 'x'\ntitle = 't'\npattern = 'p'\ndiagnosis = 'd'\nseverity = 'info'\n", "severity"),
        ("[rule]\nid = 'x'\n", "only [[fault]]"),
        ("[[fault]\n", "rules.toml"),
    ],
)
def test_parse_rules_errors(text, message):
    with pytest.raises(ValueError, match=re.escape(message)):
        parse_rules(text, "rules.toml")


def test_rule_is_frozen():
    rule = Rule("a", "b", re.compile("c"), "d")
    with pytest.raises(AttributeError):
        rule.id = "x"
