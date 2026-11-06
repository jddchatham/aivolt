# AI Volt Lab Handoff

## Current result

The Tang Primer 25K is working as a small digital voltmeter:

```text
DC source -> 0–25 V style divider -> ADS1115 -> Tang FPGA -> UART -> Linux
```

The proven test was an AAA battery:

```text
Multimeter: approximately 1.546 V
AI Volt:     1.545 V
Spread:      0.000 V
Status:      IN EXPECTED RANGE
```

The measurement was saved in the fingerprint database under `aaa`.

The FPGA is programmed into SRAM only. Power-cycling the Tang clears the design;
this is intentional and no persistent flash was programmed.

## Hardware

- Sipeed Tang Primer 25K Dock
- Gowin GW5A-25 FPGA
- ADS1115 16-bit I2C ADC breakout
- Blue resistor-divider module labelled `S`, `+`, `-`
- USB data cable
- AAA/other small batteries for safe testing

Measured divider resistors:

```text
Upper: 29.78 kOhm
Lower:  7.38 kOhm
Ratio: approximately 5.035:1
```

The divider's advertised “25 V” rating assumes a higher-voltage ADC input. With
the ADS1115 powered at 3.3 V, do not apply 25 V. The current documented prototype
limit is 15 V quiet bench DC, not automotive transient voltage.

## Confirmed Tang pin assignments

| Function | FPGA pin / connection |
|---|---|
| 50 MHz clock | E2 |
| READY diagnostic LED | E8 |
| ADS1115 SDA | K11 |
| ADS1115 SCL | L11 |
| UART TX | C3 |
| Tang supply to ADS1115 | 3V3 |
| Common return | GND |

Middle 2x6 Dock header, underside labels:

```text
Top:    A11  E11  K11  L5  GND  3V3
Bottom: A10  E10  L11  K5  GND  3V3
```

## ADS1115 wiring

```text
Tang 3V3  -> ADS1115 VDD
Tang GND  -> ADS1115 GND
Tang GND  -> ADS1115 ADDR   (I2C address 0x48)
Tang K11  -> ADS1115 SDA
Tang L11  -> ADS1115 SCL
ADS1115 A0 -> divider S
ADS1115 GND -> divider -
divider + -> leave disconnected
```

Measured source wiring:

```text
source positive (+) -> divider screw-terminal VCC
source negative (-) -> divider screw-terminal GND
```

For the AAA test, source voltage was approximately 1.546 V and divider `S` to
divider GND was approximately 310 mV. ADS1115 A0 to GND was also approximately
310 mV. This verified the analog wiring.

## FPGA designs

`ai_volt_meter.fs` is the original known-good fixed-range recovery image. It
outputs four raw hexadecimal digits and uses the ADS1115 +/-2.048 V range; with
the 5.035:1 divider it saturates at roughly 10.3 V external input.

`ai_volt_meter_autorange.fs` is the compiled auto-ranging image. It starts wide
and changes ADS1115 PGA ranges to improve low-voltage resolution. UART lines are
tagged `W:`, `M:`, or `L:` followed by four hexadecimal digits. The design limit
is 15 V external quiet DC because the divider output must remain comfortably
below the 3.3 V ADS1115 supply.

Source files are in `source/`:

```text
ads1115_top.v                 original design
ads1115_autorange_top.v      auto-ranging design
ads1115.cst                  constraints
```

## Desktop tools

Folder:

```text
~/Desktop/a.i. tang engineering/
```

The Omarchy menu entry **AI Volt** and the terminal command `aivolt`:

1. Load `ai_volt_meter_autorange.fs` into FPGA SRAM.
2. Display the full wiring checklist.
3. Wait for the user to connect the source.
4. Read five UART samples.
5. Report median voltage and spread.
6. Ask what is being measured and assign a name/ID.
7. Save timestamped history to `voltage_fingerprints.sqlite3`.
8. Offer another measurement without unplugging the Tang.

Run manually if needed:

```bash
openFPGALoader -b tangprimer25k "$HOME/Desktop/a.i. tang engineering/ai_volt_meter_autorange.fs"
python "$HOME/Desktop/a.i. tang engineering/ai_volt_meter.py"
```

The menu launcher is:

```text
~/.local/bin/aivolt
```

The software fingerprint is a measurement history and rule-based advisory. It
is not a chemical battery identity or a definitive health diagnosis.

## Automotive interpretation

For a nominal 12 V lead-acid automotive battery, the script treats roughly
12.4–12.9 V as a plausible rested range. A confirmed reading near 3 V is flagged
critically low, but the user must first verify polarity, leads, and the reading
with a multimeter. Voltage alone cannot prove capacity or cranking health.

Do not connect this prototype to a running car, alternator, charger, or unknown
source. It has no dependable reverse-polarity, short-circuit, load-dump, or
automotive surge protection. A diode alone does not prevent a short. A production
PCB needs a fuse/PTC, reverse-polarity protection, series current limiting,
external Schottky clamps, and automotive transient protection.

## AD9226 status

An AD9226 “2-channel high-speed 12-bit 65 MSPS ADC” module was purchased, but it
is **not connected**. Keep the ADS1115 installed for now.

The AD9226 is not an ADS1115 replacement. It normally needs 5 V analog power,
digital-driver power, an external sample clock, careful layout, and a parallel
12-bit output bus. Do not connect it to Tang 3.3 V or the ADS1115 SDA/SCL wiring
until the exact module schematic and pinout are identified.

## Safe operating procedure

1. Use only an isolated low-voltage battery for current testing.
2. Confirm polarity with a multimeter before connecting the source.
3. Connect source positive to divider VCC and negative to divider GND.
4. Keep the external source at or below 15 V for this prototype.
5. Never use mains voltage.
6. Never connect a running vehicle or alternator.
7. Disconnect the measured source before moving its wires.
8. Leave Tang-to-ADS1115 wiring alone while changing only the source.
9. Unplug USB before changing Tang/ADS1115 wiring; SRAM will need reloading.

## Troubleshooting order

If the software reports approximately zero:

1. Measure the source directly.
2. Measure divider `S` to divider GND; a 1.546 V AAA should produce about 310 mV.
3. Measure ADS1115 A0 to GND; it should match divider `S`.
4. Check `/dev/ttyUSB1` after USB reconnect.
5. Reload SRAM through the **AI Volt** menu if power was removed.

If readings jump, record the raw samples, check continuity with power removed,
inspect Dupont contacts, and compare against a multimeter. Change one thing at a
time and preserve the original fixed bitstream as recovery.
