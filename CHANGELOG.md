# Changelog

## 0.1.0 — unreleased

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
