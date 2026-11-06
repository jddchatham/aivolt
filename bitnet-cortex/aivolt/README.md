# AI Volt Meter — Tang Primer 25K + ADS1115

This folder contains the proven FPGA bitstream and the exact source files used
to build it on Omarchy/Arch Linux.

## What this design does

```text
Voltage input -> 5:1 divider -> ADS1115 -> I2C -> Tang Primer 25K
              -> UART -> FT2232 USB -> Linux /dev/ttyUSB1
```

The FPGA configures the ADS1115 for single-ended A0-to-GND measurements,
reads the signed 16-bit conversion register, and sends the raw value as four
hexadecimal digits at 115200 baud.

Example output:

```text
1334
1335
1334
```

## Included files

- `ai_volt_meter.fs` — proven SRAM-loadable FPGA bitstream
- `ai_volt_meter_autorange.fs` — compiled auto-ranging bitstream (0–15 V design limit)
- `ai_volt_meter.py` — interactive measurement, guidance, and fingerprint logger
- `source/ads1115_top.v` — Verilog source
- `source/ads1115_autorange_top.v` — auto-ranging Verilog source
- `source/ads1115.cst` — FPGA pin constraints

The bitstream is temporary when loaded with the command below. It does not
write persistent flash and disappears when the board is power-cycled.

## AI Volt Lab (dashboard front end)

`~/.local/bin/aivolt-lab` (desktop entry: "AI Volt Lab") is a `gum`-based
menu dashboard over the same pieces described below — bitstream loading,
`ai_volt_meter.py`, and `voltage_fingerprints.sqlite3` — instead of the
single linear script. It adds:

- a status panel (serial port present, which bitstream was loaded this
  session, how many fingerprint records exist)
- a bitstream picker (proven vs. auto-ranging) with a load spinner
- fingerprint history browsing per identity, including a min/max sparkline
  trend built from `average_voltage` (or `volts` for pre-fingerprint-engine
  rows)
- a live raw-ADC-stream viewer (`stty` + `cat` on `/dev/ttyUSB1`, Ctrl+C to
  stop without exiting the dashboard)
- hardware diagnostics (FTDI `lsusb` check, `/dev/ttyUSB*` presence, on-demand
  `openFPGALoader --detect`)
- a database summary grouped by identity

It requires `gum` (https://github.com/charmbracelet/gum). The plain
`~/.local/bin/aivolt` script (below) still exists as the minimal linear
guided flow.

## Components used

- Sipeed Tang Primer 25K Dock with GW5A-25 FPGA
- ADS1115 16-bit I2C ADC breakout
- 0–25 V style voltage-divider module
  - measured upper resistor: 29.78 kOhm
  - measured lower resistor: 7.38 kOhm
  - measured division ratio: approximately 5.035:1
- Jumper wires
- USB-C data cable
- Optional AA/AAA battery for a safe initial test
- Multimeter for wiring and voltage verification

## Verified FPGA pins

| Function | FPGA pin |
|---|---|
| 50 MHz clock | E2 |
| READY diagnostic LED | E8 |
| I2C SDA | K11 |
| I2C SCL | L11 |
| UART TX to USB debugger | C3 |

## Wiring

Always unplug USB before changing wiring.

### ADS1115 to the middle PMOD connector

Looking at the labelled underside of the Dock, the middle 2x6 group is:

```text
Top:    A11  E11  K11  L5  GND  3V3
Bottom: A10  E10  L11  K5  GND  3V3
```

Connect:

```text
ADS1115 VDD  -> Tang 3V3
ADS1115 GND  -> Tang GND
ADS1115 SDA  -> Tang K11
ADS1115 SCL  -> Tang L11
ADS1115 ADDR -> Tang GND   (selects I2C address 0x48)
```

Do not power the ADS1115 from 5 V while its I2C lines are connected directly
to the 3.3 V FPGA. The breakout's SDA and SCL pull-ups were experimentally
confirmed at 3.29 V.

### Voltage-divider module to ADS1115

The divider header is labelled `S`, `+`, and `-`. The `+` header pin is not
used in this setup.

```text
Divider S -> ADS1115 A0
Divider - -> ADS1115 GND
Divider + -> leave disconnected
```

Voltage being measured connects to the divider screw terminal:

```text
Source positive -> screw-terminal VCC
Source negative -> screw-terminal GND
```

For the first test, use an isolated 1.5 V battery. Never test mains voltage.

## Electrical limits and safety

The divider module may be advertised for 25 V, but a 25 V input would produce
about 4.97 V at the 3.3 V-powered ADS1115 and is unsafe. The original proven
bitstream uses +/-2.048 V and measures only to approximately 10 V. The new
auto-ranging bitstream starts at +/-4.096 V and selects narrower ranges when
safe for better resolution. Its documented external-input maximum is 15 V.

The 15 V limit is for quiet, protected bench DC only. The divider module does
not provide automotive surge, load-dump, reverse-polarity, or ground-loop
protection. Never connect this prototype to a running vehicle or alternator,
and never use it on mains voltage.

Do not connect:

- mains voltage
- unknown wall adapters
- negative voltages without suitable protection
- sources without a shared reference unless isolation is provided
- anything while moving loose wires on a powered board

For a production PCB, add a fuse or current-limiting resistor, transient
protection, reverse-polarity protection, input filtering, and suitable creepage
and clearance for the intended voltage category.

## Load the proven bitstream into SRAM

Connect the Tang Dock by USB, then run:

```bash
openFPGALoader -b tangprimer25k "$HOME/Desktop/a.i. tang engineering/ai_volt_meter.fs"
```

Successful output ends with `100%`, `Done`, and `DONE`.

Do not add a flash option unless persistent programming is deliberately being
tested. The documented workflow here is SRAM-only.

## Use the auto-ranging logger

The original `ai_volt_meter.fs` remains the known-good recovery image. To use
the new three-range UART format and interactive logger, load:

```bash
openFPGALoader -b tangprimer25k "$HOME/Desktop/a.i. tang engineering/ai_volt_meter_autorange.fs"
```

Then start:

```bash
python "$HOME/Desktop/a.i. tang engineering/ai_volt_meter.py"
```

The program asks what is being measured and for a name/ID. It listens for
3 seconds (`WINDOW_SECONDS` in `ai_volt_meter.py`), pulling in every valid
reading the FPGA streams during that window (at least 5, or it reports an
error), then builds a fingerprint record from that batch:

```text
sample_count       number of readings collected in the window
current_voltage    the last reading in the window
minimum_voltage    lowest reading in the window
maximum_voltage    highest reading in the window
average_voltage    mean of all readings in the window
voltage_range      maximum_voltage - minimum_voltage
stability          population standard deviation of the readings (volts)
```

Guidance (LOW/NORMAL/OVER LIMIT/etc.) is evaluated against `average_voltage`.
The full record, plus timestamp and identity, is stored in
`voltage_fingerprints.sqlite3` in this folder. Rows written before this
schema existed keep only `volts`/`spread` and show as
"(pre-fingerprint-engine record)" in the history printout.

For an automotive profile it requires confirmation that the battery is
disconnected from the vehicle and charger. A low reading is still displayed;
for example, a confirmed 3 V reading on a nominal 12 V battery is flagged as
critically low. Recheck such results with a multimeter before acting on them.

The "fingerprint" is measurement history and window statistics, not a unique
chemical identity or a machine-learning diagnosis. Battery voltage alone
cannot establish capacity, cranking ability, internal resistance, or whether
charging is safe. Inspect for damage, leakage, freezing, or overheating and
follow the battery/charger maker's instructions.

Planned future fingerprint fields (not yet implemented, and not achievable
with the current single-ended, low-rate ADS1115 UART stream without firmware
changes): ripple, timing, frequency, duty cycle, waveform shape, and protocol
hints. Each of those needs a much higher and more deterministic sample rate
than the current design provides, so they belong to a later hardware/firmware
milestone, not this software-only one.

## Read raw ADC values on Linux

After reconnecting USB, configure the UART channel:

```bash
stty -F /dev/ttyUSB1 115200 cs8 -cstopb -parenb raw -echo
```

Display values continuously:

```bash
cat /dev/ttyUSB1
```

Stop with `Ctrl+C`.

If `ttyUSB1` is absent, unplug and reconnect USB, then check:

```bash
ls -l /dev/ttyUSB0 /dev/ttyUSB1
```

The tested Dock exposes FTDI interface 1 as `/dev/ttyUSB1`. Device numbering
can change if other USB serial adapters are connected. A stable path may be
available under `/dev/serial/by-id/`.

## Convert raw hexadecimal to voltage

The ADS1115 setting is +/-2.048 V, giving 62.5 microvolts per count.
Treat the received 16-bit value as signed two's-complement.

```text
ADC voltage = signed_raw * 0.0000625 V
Input voltage = ADC voltage * 5.035
```

Example:

```text
raw hex = 1334
raw decimal = 4916
ADC voltage = 4916 * 0.0000625 = 0.30725 V
input voltage = 0.30725 * 5.035 = approximately 1.547 V
```

The multimeter comparison during bring-up was approximately 1.555 V.

Values such as `FFFF`, `FFFE`, and `0001` near grounded input mean -1, -2,
and +1 counts and are normal small zero-offset/noise readings.

## Rebuild from source

Required working tools:

- Yosys 0.66 or compatible
- nextpnr-himbaechel with Gowin GW5A support
- Apycula 0.33 and `gowin_pack`
- openFPGALoader

The proven local paths are:

```text
nextpnr: /home/user/nextpnr/build/nextpnr-himbaechel
gowin_pack: /home/user/fpga-tools/bin/gowin_pack
```

Build in a separate directory so this reference folder remains clean:

```bash
mkdir -p "$HOME/fpga/ai_volt_meter_build"
cp "$HOME/Desktop/a.i. tang engineering/source/ads1115_top.v" "$HOME/fpga/ai_volt_meter_build/"
cp "$HOME/Desktop/a.i. tang engineering/source/ads1115.cst" "$HOME/fpga/ai_volt_meter_build/"
cd "$HOME/fpga/ai_volt_meter_build"
```

Synthesize:

```bash
yosys -p 'read_verilog ads1115_top.v; synth_gowin -family gw5a -top ads1115_top -json ads1115.json'
```

Place and route:

```bash
/home/user/nextpnr/build/nextpnr-himbaechel \
  --device GW5A-LV25MG121NC1/I0 \
  --json ads1115.json \
  --write ads1115_pnr.json \
  --freq 50 \
  -o cst=ads1115.cst \
  -o sspi_as_gpio
```

Pack:

```bash
/home/user/fpga-tools/bin/gowin_pack \
  -d GW5A-25A \
  --sspi_as_gpio \
  --ready_as_gpio \
  -o ai_volt_meter.fs \
  ads1115_pnr.json
```

Load into SRAM:

```bash
openFPGALoader -b tangprimer25k ai_volt_meter.fs
```

If rebuilding nextpnr itself is ever necessary, use `make -j2` or `make -j1`.
Do not use `make -j$(nproc)` on this machine; it previously caused severe
resource pressure or an apparent system crash.

## Troubleshooting checklist

Work from measurements and logs. Change only one thing at a time.

### FPGA is not detected

Run:

```bash
openFPGALoader --detect
```

Expected device:

```text
manufacturer Gowin
family GW5A
model GW5A-25
idcode 0x1281b
```

If FTDI cannot be opened:

1. Check that the USB cable supports data, not only charging.
2. Unplug and reconnect it.
3. Check `lsusb` for `0403:6010`.
4. Ensure no other loader or serial program holds the interface.
5. Check kernel messages with `journalctl -k -n 80 --no-pager`.

### Bitstream loads but UART is silent

1. Confirm loading reached 100%.
2. Re-run the `stty` command after every USB reconnect.
3. Confirm `/dev/ttyUSB1` exists.
4. Close other terminal programs using that port.
5. Verify UART TX remains constrained to FPGA pin C3.
6. Use `fuser /dev/ttyUSB1` to find a process holding the port.
7. Be aware that old UART bytes may remain buffered; drain them before
   judging a newly loaded design.

### READY LED does not blink

E8 blinks only after a complete acknowledged I2C conversion read near zero.
Once a nonzero voltage is intentionally applied, the current near-zero LED
test may remain steady even while UART data is valid. UART output is the main
measurement result.

For an I2C failure:

1. Measure ADS1115 VDD-to-GND: expected approximately 3.3 V.
2. Measure idle SDA-to-GND: expected approximately 3.3 V.
3. Measure idle SCL-to-GND: expected approximately 3.3 V.
4. Confirm ADDR is connected to GND for address 0x48.
5. Confirm SDA goes to K11 and SCL goes to L11.
6. Confirm the FPGA uses open-drain IOBUFs; never drive I2C high actively.
7. Inspect for loose Dupont contacts or unsoldered header pins.

### Readings jump or fail intermittently

Ask the assisting AI to separate electrical, protocol, and software evidence:

1. Record the exact raw UART sequence instead of reporting only “unstable.”
2. Compare simultaneous multimeter readings at source input and ADS1115 A0.
3. Gently move one wire at a time while watching readings to identify a bad
   contact. Do not move power wiring on a live board if it could short.
4. Power down and use continuity mode end-to-end on every wire.
5. Measure resistance from each adjacent signal pair to rule out solder bridges.
6. Check whether SDA or SCL ever remains near 0 V when idle, indicating a stuck
   bus, reversed connection, short, or unpowered peripheral.
7. Verify common ground among Tang, ADS1115, divider, and measured source.
8. Short A0 to ADS1115 GND as a controlled test. Expected raw values should be
   near `0000`, with occasional `FFFF`, `FFFE`, or small positive counts.
9. Substitute a 1.5 V battery as a quiet known source. Expected divider output
   is around 0.30 V and raw code around `0x1300`–`0x1400`.
10. Rebuild only after hardware checks pass. A wiring fault should not be
    “fixed” by random HDL changes.

### AI troubleshooting protocol

When handing this project to another AI, provide:

- the exact command used
- complete error output
- whether the error occurred during synthesis, routing, packing, JTAG, I2C,
  UART, or analog measurement
- measured VDD, SDA idle, SCL idle, A0, and source voltage
- current wiring photo
- whether the board was power-cycled since SRAM programming
- the last known-good SHA-256 of the reference bitstream

Reference `ai_volt_meter.fs` SHA-256:

```text
c4cde39de69a73e6462321326b970afa60c7260ef7a45f2dfdf584779f214399
```

An AI should first reproduce the failure, compare against the known-good
bitstream and wiring, and make one controlled change at a time. It should not
write persistent FPGA flash, apply unknown voltages, alter several pins at
once, or assume that a successful JTAG load proves the analog and UART paths.

## Known-good bring-up evidence

- FPGA JTAG detection: GW5A-25, IDCODE `0x1281b`
- FPGA clock: 50 MHz on E2
- ADS1115 address 0x48 acknowledged
- Configuration bytes `C5 83` acknowledged
- Grounded A0 read near raw zero
- Fixed UART `OK` test received on `/dev/ttyUSB1`
- Raw UART values received successfully
- 1.555 V battery produced approximately 0.311 V divider output
- FPGA raw result around `0x1334`, calculated as approximately 1.547 V
