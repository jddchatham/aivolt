# AI Volt

Launcher for the AI Volt Lab voltmeter: loads the auto-ranging FPGA
design into the Tang Primer 25K and runs the measurement/save loop.

Also included: `bitnet-cortex/aivolt/` — the AI Volt Lab project files
(FPGA bitstreams, meter Python, fingerprint DB, docs). For the full
Cortex 2.0 bridge, see the BitNet4 repo (`aivolt/scripts/`).

## Install

```sh
# 1. project folder the script expects:
cp -r bitnet-cortex/aivolt "$HOME/Desktop/a.i. tang engineering"
# 2. launcher:
cp aivolt ~/.local/bin/ && chmod +x ~/.local/bin/aivolt
```

Requires: `openFPGALoader`, Python 3, pyserial (for the meter),
Tang Primer 25K + ADS1115 divider hardware on /dev/ttyUSB1.

## Use

```sh
aivolt     # loads bitstream, prompts for wiring, then measures
```

15 V maximum. Never connect mains or a running vehicle/alternator.
First test: a 1.5 V battery (expect ~1.5 V, saved as fingerprint `aaa`).
