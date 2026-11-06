#!/usr/bin/env python3
"""Interactive Tang/ADS1115 voltage logger and fingerprint database."""

import datetime as dt
import os
import re
import select
import sqlite3
import statistics
import sys
import termios
import time
from pathlib import Path

DIVIDER_RATIO = 5.035
SERIAL_DEVICE = "/dev/ttyUSB1"
DB_PATH = Path(__file__).with_name("voltage_fingerprints.sqlite3")
SCALE = {"L": 0.00003125, "M": 0.0000625, "W": 0.000125}
WINDOW_SECONDS = 3.0
MIN_FINGERPRINT_SAMPLES = 5
MAX_FINGERPRINT_SAMPLES = 2000


def choose(prompt, choices):
    while True:
        print(prompt)
        for key, text in choices.items():
            print(f"  {key}. {text}")
        answer = input("> ").strip()
        if answer in choices:
            return answer
        print("Please enter one of: " + ", ".join(choices))


def configure_serial(fd):
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] = 0
    attrs[4] = termios.B115200
    attrs[5] = termios.B115200
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 10
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIFLUSH)


def signed16(value):
    return value - 65536 if value & 0x8000 else value


def collect_window(device, duration=WINDOW_SECONDS,
                    min_samples=MIN_FINGERPRINT_SAMPLES, max_samples=MAX_FINGERPRINT_SAMPLES):
    """Collect every valid reading for `duration` seconds instead of a fixed count.

    A time window (rather than a fixed sample count) is what lets the fingerprint
    reflect how noisy/stable the source actually is, not just five arbitrary points.
    """
    fd = os.open(device, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        configure_serial(fd)
        samples, buffer = [], ""
        deadline = time.monotonic() + duration
        tagged = re.compile(r"^([LMW]):([0-9A-Fa-f]{4})$")
        legacy = re.compile(r"^([0-9A-Fa-f]{4})$")
        while time.monotonic() < deadline and len(samples) < max_samples:
            ready, _, _ = select.select([fd], [], [], 1)
            if not ready:
                continue
            buffer += os.read(fd, 256).decode("ascii", "ignore")
            lines = re.split(r"[\r\n]+", buffer)
            buffer = lines.pop()
            for line in lines:
                line = line.strip()
                match = tagged.match(line)
                if match:
                    code = signed16(int(match.group(2), 16))
                    samples.append(code * SCALE[match.group(1)] * DIVIDER_RATIO)
                else:
                    match = legacy.match(line)
                    if match:
                        code = signed16(int(match.group(1), 16))
                        samples.append(code * SCALE["M"] * DIVIDER_RATIO)
                if len(samples) >= max_samples:
                    break
        if len(samples) < min_samples:
            raise RuntimeError(
                f"received only {len(samples)} valid samples in {duration:.1f}s "
                f"(need at least {min_samples})")
        return samples
    finally:
        os.close(fd)


def build_fingerprint(samples):
    """Turn a batch of raw voltage samples into the fingerprint record."""
    return {
        "sample_count": len(samples),
        "current_voltage": samples[-1],
        "minimum_voltage": min(samples),
        "maximum_voltage": max(samples),
        "average_voltage": statistics.fmean(samples),
        "voltage_range": max(samples) - min(samples),
        "stability": statistics.pstdev(samples) if len(samples) > 1 else 0.0,
    }


NEAR_ZERO_VOLTS = 0.02  # well above ADC noise floor (~0.0002 V), well below any real connected source


def assessment(profile, volts):
    if volts < -0.05:
        return "POLARITY/WIRING ERROR", "Disconnect power and verify polarity and common ground."
    if volts > 15.0:
        return "OVER LIMIT", "Disconnect immediately. This prototype is limited to 15 V."
    if profile == "automotive":
        if volts < 1.0:
            return "CHECK CONNECTION", "Near zero may mean a loose lead or wrong measurement point. Verify with a multimeter."
        if volts < 10.5:
            return "CRITICALLY LOW", "Recheck the leads. If confirmed, remove the battery from service; it may be deeply discharged or damaged."
        if volts < 12.0:
            return "LOW", "Consider an appropriate smart charger after checking battery condition and manufacturer instructions."
        if volts < 12.4:
            return "PARTIALLY CHARGED", "Charging may be appropriate. A resting voltage is most useful after surface charge settles."
        if volts <= 12.9:
            return "NORMAL RESTING RANGE", "Voltage looks plausible for a rested 12 V lead-acid battery; voltage alone does not prove health."
        return "CHARGING/RECENTLY CHARGED", "If the engine is running, disconnect this unprotected prototype; automotive transients can damage it."
    if volts < NEAR_ZERO_VOLTS:
        return "CHECK CONNECTION", (
            "Reading is near 0 V, close to the ADC's noise floor. If a source should be connected, "
            "verify leads, polarity, and common ground before trusting this as a real reading. "
            "A deliberately grounded or disabled test point reading 0 V is expected.")
    bands = {"low": (0, 6), "medium": (5, 10), "wide": (0, 15)}
    lo, hi = bands[profile]
    if lo <= volts <= hi:
        return "IN EXPECTED RANGE", "Record saved. Compare future readings under the same conditions."
    return "OUTSIDE EXPECTED RANGE", "Verify the selected profile, wiring, and reading with a multimeter."


FINGERPRINT_COLUMNS = {
    "sample_count": "INTEGER",
    "current_voltage": "REAL",
    "minimum_voltage": "REAL",
    "maximum_voltage": "REAL",
    "average_voltage": "REAL",
    "voltage_range": "REAL",
    "stability": "REAL",
}


def ensure_schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS fingerprints (
      id INTEGER PRIMARY KEY, measured_at TEXT NOT NULL, identity TEXT NOT NULL,
      kind TEXT NOT NULL, volts REAL NOT NULL, spread REAL NOT NULL,
      status TEXT NOT NULL, note TEXT NOT NULL)""")
    existing = {row[1] for row in db.execute("PRAGMA table_info(fingerprints)")}
    for name, coltype in FINGERPRINT_COLUMNS.items():
        if name not in existing:
            db.execute(f"ALTER TABLE fingerprints ADD COLUMN {name} {coltype}")


def save(identity, kind, fp, status, note):
    with sqlite3.connect(DB_PATH) as db:
        ensure_schema(db)
        db.execute("""INSERT INTO fingerprints(
              measured_at, identity, kind, volts, spread, status, note,
              sample_count, current_voltage, minimum_voltage, maximum_voltage,
              average_voltage, voltage_range, stability)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (dt.datetime.now().astimezone().isoformat(timespec="seconds"), identity, kind,
                    fp["average_voltage"], fp["voltage_range"], status, note,
                    fp["sample_count"], fp["current_voltage"], fp["minimum_voltage"],
                    fp["maximum_voltage"], fp["average_voltage"], fp["voltage_range"],
                    fp["stability"]))
        prior = db.execute(
            """SELECT measured_at, average_voltage, status, sample_count, stability
               FROM fingerprints WHERE identity=? ORDER BY id DESC LIMIT 5""",
            (identity,)).fetchall()
    return prior


def main():
    print("AI Volt Meter — 15 V maximum, never mains voltage")
    profile_key = choose("What are you measuring?", {
        "1": "Low-voltage electronics (expected 0–6 V)",
        "2": "General DC source (expected 5–10 V)",
        "3": "12 V automotive battery (expected about 9–15 V)",
        "4": "Other protected DC source (0–15 V)",
    })
    profile = {"1": "low", "2": "medium", "3": "automotive", "4": "wide"}[profile_key]
    identity = input("Name/ID for this item (example: Car battery 1): ").strip() or "unnamed"
    if profile == "automotive":
        print("WARNING: Do not connect this unprotected prototype to a running vehicle or alternator.")
        if input("Is the battery disconnected from the vehicle/charger? Type YES: ").strip() != "YES":
            print("Stopped for safety.")
            return 2
    print(f"Reading a {WINDOW_SECONDS:.0f}s sample window from {SERIAL_DEVICE}...")
    samples = collect_window(SERIAL_DEVICE)
    fp = build_fingerprint(samples)
    status, note = assessment(profile, fp["average_voltage"])
    prior = save(identity, profile, fp, status, note)
    print(f"\nSamples:  {fp['sample_count']}")
    print(f"Current:  {fp['current_voltage']:.4f} V")
    print(f"Average:  {fp['average_voltage']:.4f} V")
    print(f"Minimum:  {fp['minimum_voltage']:.4f} V")
    print(f"Maximum:  {fp['maximum_voltage']:.4f} V")
    print(f"Range:    {fp['voltage_range']:.4f} V")
    print(f"Stability (stdev): {fp['stability']:.4f} V")
    print(f"Status: {status}\n{note}")
    if fp["voltage_range"] > 0.10:
        print("Intermittent warning: readings varied by over 0.10 V. Check contacts and verify with a multimeter.")
    print("\nRecent fingerprint history:")
    for when, value, old_status, count, stability in prior:
        if value is None:
            print(f"  {when}: (pre-fingerprint-engine record) — {old_status}")
        else:
            print(f"  {when}: {value:.3f} V (n={count}, stdev={stability:.4f}) — {old_status}")
    print(f"Database: {DB_PATH}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as exc:
        print(f"Measurement failed: {exc}", file=sys.stderr)
        print("Check /dev/ttyUSB1, reload the FPGA bitstream, and close other serial programs.", file=sys.stderr)
        raise SystemExit(1)
