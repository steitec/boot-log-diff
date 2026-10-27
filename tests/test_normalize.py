import re

import pytest

from boot_log_diff.normalize import BUILTIN_MASKS, Mask, Normalizer, clean


def test_clean_strips_ansi_carriage_returns_and_trailing_space():
    assert clean("\x1b[0;32mOK\x1b[0m  \r") == "OK"


@pytest.mark.parametrize(
    "line, expected",
    [
        ("[    1.102331] mmc2: SDHCI", "[<TS>] mmc2: SDHCI"),
        ("[12345.000001] late", "[<TS>] late"),
        ("Booting using the fdt blob at 0x43000000", "Booting using the fdt blob at <HEX>"),
        ("Loading Device Tree to 00000000bdf3f000, end x", "Loading Device Tree to <HEX>, end x"),
        ("eth0: MAC 00:1A:2b:3c:4d:5e", "eth0: MAC <MAC>"),
        ("leased 192.168.178.42 from", "leased <IP> from"),
        ("setting system clock to 2026-10-02T09:31:44 UTC (1791106304)", "setting system clock to <DATETIME>"),
        ("[2026-10-27 14:02:13.123] U-Boot", "[<DATETIME>] U-Boot"),
        ("22451712 bytes read in 241 ms (88.8 MiB/s)", "22451712 bytes read in <DURATION> (<RATE>)"),
        ("CPU: Industrial grade (-40C to 105C) at 38C", "CPU: Industrial grade (<TEMP> to <TEMP>) at <TEMP>"),
        ("Calibrating delay loop... 4789.94 BogoMIPS (lpj=1)", "Calibrating delay loop... <BOGOMIPS> (lpj=1)"),
        ("root=UUID=3f2504e0-4f89-11d3-9a0c-0305e82c3301 ro", "root=UUID=<UUID> ro"),
    ],
)
def test_builtin_masks(line, expected):
    assert Normalizer()(line) == expected


def test_does_not_mask_stable_values():
    # Device addresses, sizes, CPU counts and build dates identify the
    # firmware and hardware, so a change in them is a real deviation.
    for line in [
        "fec 30be0000.ethernet eth0: registered PHC device 0",
        "DRAM: 2 GiB",
        "smp: Brought up 1 node, 4 CPUs",
        "U-Boot 2023.04-g3a1b2c4 (Oct 02 2026 - 09:14:22 +0000)",
        "i2c i2c-1: I2C adapter",
    ]:
        assert Normalizer()(line) == line


def test_collapses_whitespace():
    assert Normalizer()("DRAM:   2  GiB") == "DRAM: 2 GiB"


def test_disable_builtin_mask():
    normalize = Normalizer(disabled={"temp"})
    assert normalize("at 38C") == "at 38C"


def test_unknown_mask_name_is_rejected():
    with pytest.raises(ValueError, match="nope"):
        Normalizer(disabled={"nope"})


def test_extra_mask_and_ignore():
    normalize = Normalizer(
        extra=[Mask("hostname", re.compile(r"epc8m-[0-9a-f]+"), "<HOST>")],
        ignore=[re.compile(r"random: crng")],
    )
    assert normalize("epc8m-00a1f3 login:") == "<HOST> login:"
    assert normalize("[    0.1] random: crng init done") is None


def test_builtin_mask_names_are_unique():
    names = [m.name for m in BUILTIN_MASKS]
    assert len(names) == len(set(names))
