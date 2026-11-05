# Changelog

## 0.3.0 — 2026-11-05

### Added

- **Faults from missing lines**: 10 new built-in faults fire when a line that
  good boards print is gone: eMMC/SD card, SATA, NVMe, Ethernet driver and
  link, USB device, PCIe link, RTC, SPI flash, CAN. A line that only changed a
  value does not count: the DUT log must have fewer matching lines than the
  golden log.
- `boot-incomplete`: the DUT log stops before the end of the golden log. The
  lines it never got to are reported once, not as one fault per driver.
- `sata-link`: COMRESET failures, link down, reduced link speed.
- Rule files: `match = "missing"` or `"unreached"` (default `"new"`), and
  `unless = [ids]` to silence a `missing` rule that another fault explains.
- Python API: `Rule.match`, `Rule.unless`, `Fault.log`.
- JSON output: faults have `log` (`dut` or `golden`), the log their line
  numbers refer to.

### Changed

- Reports name the log of a fault's lines (`golden line 11`, `dut line 62`).

## 0.2.0 — 2026-10-29

### Added

- **Known faults**: new DUT lines are matched against 23 built-in fault
  patterns (DDR training, eMMC/SD timeout and CRC, block I/O, Ethernet PHY
  and link, USB, I2C, SPI/NOR, NAND, PCIe, root/file system, boot images,
  U-Boot environment, kernel panic, watchdog, supplies, temperature, ECC,
  firmware, CPU stalls). Each match shows a title, severity and diagnosis.
- `--rules FILE` (TOML, repeatable) adds own known faults; they are checked
  before the built-in ones and replace a built-in fault with the same id.
  `--no-builtin-rules` switches the built-in list off.
- `--junit FILE`: JUnit XML report with one test case per fact, one for the
  log lines and one per known fault.
- `--html FILE`: self-contained HTML report (no scripts, light/dark).
- JSON output and `Result.summary()` have `faults`; Python API:
  `Result.faults`, `Rule`, `Fault`, `BUILTIN_RULES`, `load_rules`,
  `parse_rules`, `compare(..., rules=...)`.

### Changed

- Python 3.10 needs `tomli` to read the rule files (installed
  automatically); Python 3.11 and newer still need no dependencies.

## 0.1.0 — 2026-10-27

First version.

- Compare a DUT boot log with a golden log after masking timestamps, hex
  addresses, dates, durations, transfer rates, temperatures, MAC/IP
  addresses, UUIDs and BogoMIPS.
- Lines that only changed position are reported as moved, not as deviations
  (`--strict-order` to turn this off).
- Built-in facts: board model, U-Boot version, DRAM, kernel version, kernel
  memory, CPU count; own facts with `--fact`.
- New lines that look like errors are flagged.
- `--mask`, `--ignore`, `--no-mask`, `--json`, `--color`, DUT log from stdin.
