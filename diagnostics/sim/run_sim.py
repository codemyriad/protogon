#!/usr/bin/env python3
"""Run the UNMODIFIED badge diagnostic on a host PC against fake hardware.

    python3 sim/run_sim.py                      # clean run, see the thermal feed
    python3 sim/run_sim.py --soak 30            # longer (virtual) soak
    python3 sim/run_sim.py --crosstalk-demo     # quiet clean, aggressor shows errors
    python3 sim/run_sim.py --inject-ber 1e-6    # prove the integrity checker counts bits
    python3 sim/run_sim.py --inject-nack 1e-4   # prove NACK counting

Nothing here touches a real badge. It swaps in sim/fakehw for `machine`, patches
MicroPython's time.ticks_*/sleep_ms onto a virtual clock, and execs the
diagnostic unchanged. See the note printed at the end about what this does NOT
prove.
"""
import argparse
import os
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
DIAG = os.path.join(os.path.dirname(HERE), "protogon_thermal_test.py")
sys.path.insert(0, HERE)

import fakehw  # noqa: E402


def install_fakes(clock, faults):
    # machine module
    machine = types.ModuleType("machine")
    machine.I2C = lambda port: fakehw.FakeI2C(port, clock, faults)
    machine.Pin = fakehw.FakePin
    machine.PWM = fakehw.FakePWM
    fakehw.FakePWM._faults = faults
    sys.modules["machine"] = machine

    # system.hexpansion.config.HexpansionConfig(port).pin -> [FakePin, ...]
    sys_mod = types.ModuleType("system")
    hx = types.ModuleType("system.hexpansion")
    cfg = types.ModuleType("system.hexpansion.config")

    class HexpansionConfig:
        def __init__(self, port):
            self.port = port
            self.pin = [fakehw.FakePin() for _ in range(4)]
    cfg.HexpansionConfig = HexpansionConfig
    sys_mod.hexpansion = hx
    hx.config = cfg
    sys.modules["system"] = sys_mod
    sys.modules["system.hexpansion"] = hx
    sys.modules["system.hexpansion.config"] = cfg

    # MicroPython time extensions backed by the virtual clock
    time.ticks_ms = clock.now
    time.ticks_add = lambda a, b: a + b
    time.ticks_diff = lambda a, b: a - b
    time.sleep_ms = lambda ms: clock.advance(ms)


def main():
    ap = argparse.ArgumentParser(description="Run the Protogon diagnostic against fake hardware.")
    ap.add_argument("--soak", type=float, default=8.0, help="virtual seconds per soak window")
    ap.add_argument("--port", type=int, default=1)
    ap.add_argument("--no-crosstalk", action="store_true")
    ap.add_argument("--no-render", action="store_true", help="skip the ASCII image")
    ap.add_argument("--inject-ber", type=float, default=0.0, help="always-on bit-error rate")
    ap.add_argument("--inject-nack", type=float, default=0.0, help="NACK probability per transaction")
    ap.add_argument("--crosstalk-demo", action="store_true",
                    help="clean when quiet, errors only when the aggressor is on")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    clock = fakehw.VClock()
    faults = fakehw.Faults(
        base_ber=args.inject_ber,
        aggr_ber=1e-5 if args.crosstalk_demo else 0.0,
        nack_rate=args.inject_nack,
        seed=args.seed,
    )
    install_fakes(clock, faults)

    src = open(DIAG).read()
    ns = {"__name__": "protogon_sim"}      # not __main__, so it won't auto-run
    exec(compile(src, DIAG, "exec"), ns)

    # Override the diagnostic's config for a quick, host-friendly run.
    ns["PORT"] = args.port
    ns["SOAK_SECONDS"] = args.soak
    ns["DO_CROSSTALK"] = not args.no_crosstalk
    ns["RENDER_FRAMES"] = not args.no_render

    # Take the golden snapshot fault-free. The sim's job is proving the
    # counters count what we inject; if injected faults could corrupt the
    # baseline itself, every later compare would flag phantom mismatches and
    # the measured BER would drift to ~2x the injected rate.
    orig_snapshot = ns["snapshot_golden"]

    def clean_snapshot(i2c):
        saved = (faults.base_ber, faults.aggr_ber, faults.nack_rate)
        faults.base_ber = faults.aggr_ber = faults.nack_rate = 0.0
        try:
            return orig_snapshot(i2c)
        finally:
            faults.base_ber, faults.aggr_ber, faults.nack_rate = saved
    ns["snapshot_golden"] = clean_snapshot

    print("### SIMULATION -- fake hardware, virtual clock. Not a real badge. ###\n")
    ns["main"]()
    print("\n### END SIMULATION. This proves the script's LOGIC only -- it says")
    print("### nothing about real 133 kHz bus timing or signal integrity. ###")


if __name__ == "__main__":
    main()
