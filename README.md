# boot-log-diff

[![CI](https://github.com/steitec/boot-log-diff/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/steitec/boot-log-diff/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/boot-log-diff)](https://pypi.org/project/boot-log-diff/)
[![Python](https://img.shields.io/pypi/pyversions/boot-log-diff)](https://pypi.org/project/boot-log-diff/)
[![License](https://img.shields.io/pypi/l/boot-log-diff)](https://github.com/steitec/boot-log-diff/blob/main/LICENSE)

Compare the serial boot log of an embedded board with the log of a
known-good board — the "golden log" — and see only what really differs.
Timestamps, load addresses, transfer rates, dates, MAC and IP addresses are
masked first, so a missing driver, a wrong RAM size or a new error message
is not buried under a few hundred lines that change on every boot. Known
fault patterns — a PHY that is not found, an eMMC timeout, failed DDR
training — come with a plain-text diagnosis, and the result can go to CI as
a JUnit XML or HTML report.

```console
$ boot-log-diff golden.log faulty.log --mask 'epc8m-[0-9a-f]+'
golden: golden.log
dut:    faulty.log

Facts that differ:
  dram    2 GiB  ->  1 GiB
  memory  2097152K  ->  1048576K

Known faults:
  [error] Ethernet PHY not found (eth-phy), dut line 50
      The MAC cannot talk to the PHY over MDIO. Check the PHY supply and its
      reset line, the reference clock (25/50 MHz), the MDIO/MDC solder
      joints and the PHY address strapping.
  [error] eMMC/SD card does not respond (timeout) (mmc-timeout), dut lines 62, 63
      The host controller gets no answer from the card. For an SD slot: card
      missing or not seated, card-detect wired wrong, no card supply. For
      eMMC: VCC/VCCQ missing, a broken CLK/CMD line, or solder joints under
      the eMMC.

@@ golden line 16, dut line 16 @@
-  DRAM:  2 GiB
+  DRAM:  1 GiB

@@ golden line 39, dut line 39 @@
-  [    0.000000] Memory: 1987532K/2097152K available (16128K kernel code, ...)
+  [    0.000000] Memory: 939212K/1048576K available (16128K kernel code, ...)

@@ golden line 50, dut line 50 @@
-  [    1.312003] Micrel KSZ9031 Gigabit PHY 30be0000.ethernet-1:07: attached PHY driver
+! [    1.313120] fec 30be0000.ethernet eth0: Unable to connect to phy

@@ golden line 62, dut line 62 @@
-  [    3.120345] fec 30be0000.ethernet eth0: Link is Up - 1Gbps/Full - flow control rx/tx
-  [    3.611233] IPv6: ADDRCONF(NETDEV_CHANGE): eth0: link becomes ready
+! [    4.611290] mmc1: Timeout waiting for hardware interrupt.
+! [    4.612001] mmc1: error -110 whilst initialising SD card

2 facts changed, 5 missing, 5 new (3 look like errors), 1 moved, 2 known faults
moved lines are drivers probing in another order; --strict-order shows them
```

The two logs in [`examples/`](examples) are 67 lines each; a plain `diff`
marks 60 lines in them. boot-log-diff reports the four places
that matter: half the RAM, an Ethernet PHY that is not found, and an SD card
slot that times out — and says where to look for the last two.

## Why

In board repair and production test, the boot log is often the first and
cheapest diagnosis: connect the serial console, power up, and compare with a
board that works. Doing that by eye is slow, and `diff` is useless because
every kernel timestamp differs. boot-log-diff:

- **masks boot-to-boot noise** — kernel timestamps, hex addresses, dates,
  durations, transfer rates, temperatures, MAC/IP addresses, UUIDs, BogoMIPS
- **ignores driver probe order** — drivers probing in parallel do not keep
  their order; lines that only moved are counted, not reported as faults
- **compares key facts** — RAM size, memory seen by the kernel, CPU count,
  board model, U-Boot and kernel version, plus your own
- **flags error-looking lines** — new lines with *error*, *fail*, *timeout*,
  *unable*, *not found* and the like are marked with `!`
- **diagnoses known faults** — 23 built-in patterns for DRAM, eMMC/SD, NAND,
  SPI flash, Ethernet PHY, USB, I2C, PCIe, supplies, temperature, file system
  and kernel crashes, each with what to check on the board; add your own
- **fits into CI and test scripts** — exit status 0/1/2, JSON, JUnit XML and
  HTML reports, reads the DUT log from stdin, no dependencies on Python 3.11+

## Install

```console
$ pip install boot-log-diff
```

Or run it from a clone without installing: `python -m boot_log_diff` with
`src` on `PYTHONPATH`.

## Usage

```console
$ boot-log-diff GOLDEN DUT [options]
```

| Option | Meaning |
|---|---|
| `--mask REGEX` | also mask matches of REGEX, e.g. serial numbers or host names |
| `--ignore REGEX` | leave out lines matching REGEX |
| `--no-mask NAME` | switch off a built-in mask (`datetime`, `timestamp`, `uuid`, `mac`, `hex`, `ip`, `duration`, `rate`, `temp`, `bogomips`) |
| `--fact NAME=REGEX` | compare the first group of REGEX as a named fact |
| `--strict-order` | report lines that only moved as missing and new |
| `--rules FILE` | known faults from a TOML file, checked before the built-in ones |
| `--no-builtin-rules` | do not use the built-in known faults |
| `--json` | print the result as JSON |
| `--junit FILE` | also write a JUnit XML report |
| `--html FILE` | also write an HTML report |
| `--color auto\|always\|never` | colour the text output (`NO_COLOR` is respected) |

All options that take a pattern, and `--rules`, can be given more than once. Patterns are
Python regular expressions and are matched against each line with
`re.search`.

Exit status: `0` no deviations, `1` deviations found, `2` usage or input
error (bad regex, bad rules file, missing file, report not writable).

### Capturing the DUT log

Any capture works — minicom, picocom, PuTTY logging, `grabserial`. ANSI
colour codes and carriage returns are removed, blank lines are skipped, and
capture-tool timestamps in ISO format are masked. To compare straight from
the serial port:

```console
$ timeout 60 cat /dev/ttyUSB0 | boot-log-diff golden.log -
```

### Your own facts

Built-in facts are `model`, `u-boot`, `dram`, `kernel`, `memory` and `cpus`.
Add anything that shows up in your boot log:

```console
$ boot-log-diff golden.log dut.log \
    --fact 'fpga=FPGA bitstream v(\S+)' \
    --fact 'emmc=mmcblk\d: \S+ \S+ (\S+ GiB)'
```

### Known faults

New lines in the DUT log — lines that are not in the golden log — are
matched against a list of known faults. A match is listed with a title, a
severity (`error` or `warning`) and a diagnosis: what usually causes this
message and what to check on the board. A line that is also in the golden
log is not a fault of this board, so a warning your healthy boards print
anyway does not show up.

The built-in list covers DDR training, eMMC/SD timeouts and CRC errors,
block I/O errors, Ethernet PHY and link, USB enumeration and over-current,
I2C devices that do not answer, SPI/NOR and NAND flash, PCIe link, root file
system and file system errors, corrupt boot images, U-Boot environment,
kernel panics, watchdog resets, supplies and regulators, over-temperature,
memory ECC errors, missing firmware and CPU stalls. `boot-log-diff --help`
lists their ids; the definitions are in
[`faults.toml`](src/boot_log_diff/faults.toml).

Add what you know about your own boards in a TOML file:

```toml
[[fault]]
id = "fpga-config"
title = "FPGA not configured"
pattern = 'fpga.*done pin (?:low|timeout)'
diagnosis = """
The FPGA did not load its bitstream. Check the configuration flash and the
1.8 V auxiliary supply (TP14)."""

[[fault]]
id = "eth-phy"           # same id as a built-in fault: replaces it
title = "Ethernet PHY not found"
pattern = 'unable to connect to phy'
diagnosis = "On rev C boards: R212 (PHY reset pull-up) is often cracked."
severity = "warning"
```

```console
$ boot-log-diff golden.log dut.log --rules our-boards.toml
```

Patterns are Python regular expressions, matched case-insensitively. Own
rules are checked before the built-in ones; a line counts for the first rule
that matches.

### Reports for CI

`--junit FILE` writes a JUnit XML report that GitLab, Jenkins, GitHub
Actions (with a test-report action) and most test management tools can
show: one test case per fact, one for the log lines and one per known fault,
so a failing board shows *Ethernet PHY not found* rather than "diff failed".
`--html FILE` writes a single self-contained page (no scripts, light and
dark mode) to attach to a test record or a repair ticket. Both are written
in addition to the normal output.

GitLab CI:

```yaml
boot-check:
  script:
    - boot-log-diff golden.log dut.log --junit boot.xml --html boot.html
  artifacts:
    when: always
    reports:
      junit: boot.xml
    paths: [boot.html]
```

### In a Python test

```python
import re

from boot_log_diff import Normalizer, compare

result = compare(
    golden_text,
    dut_text,
    normalizer=Normalizer(ignore=[re.compile(r"random: crng")]),
)
assert not result.has_deviations, result.summary()
```

`result.facts`, `result.hunks` (with `removed` and `added` lines, each with
line number, text and an `error` flag), `result.faults` (each with its `rule`
and the matching `lines`) and `result.moved` hold the details. Own rules come
from `load_rules(path)` or `parse_rules(text)`; pass them as
`compare(..., rules=own + list(BUILTIN_RULES))`. `render_junit` and
`render_html` in `boot_log_diff.report` produce the reports.

## Limitations

- Lines are compared as a whole after masking. A line that changed in one
  value shows up as one missing and one new line.
- The error flag and the known faults are pattern matches, not an
  understanding of the message. A diagnosis says where to look first; it
  is not a verdict.
- Known faults only look at new lines. A fault that shows as a *missing*
  line (a driver that no longer probes) is in the diff, without a diagnosis.
- One golden log per comparison. If healthy boards differ among themselves
  (other eMMC vendor, optional module), mask or ignore that line.

## License

MIT
