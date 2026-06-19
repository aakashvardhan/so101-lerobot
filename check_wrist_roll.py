#!/usr/bin/env python3
"""Live overload/health check for a single Feetech motor (default: wrist_roll, ID 5).

Reads Present_Load, Present_Current, Present_Temperature, Present_Voltage and the
Status (hardware error) register and flags overload conditions.
"""

import argparse
import time

BAUDRATE = 1_000_000
PROTOCOL = 0

# STS/SMS control table (addr, size)
ADDR = {
    "Present_Position": (56, 2),
    "Present_Load": (60, 2),
    "Present_Voltage": (62, 1),
    "Present_Temperature": (63, 1),
    "Status": (65, 1),
    "Present_Current": (69, 2),
    "Torque_Enable": (40, 1),
    "Overload_Torque": (36, 1),  # EEPROM, %
    "Max_Temperature_Limit": (13, 1),
}

# Feetech STS hardware-error / status bits
ERROR_BITS = {
    0x01: "Voltage",
    0x02: "Angle/Sensor",
    0x04: "Overheat",
    0x08: "Overcurrent",
    0x10: "Angle",
    0x20: "Overload",
}


def decode_signed_magnitude(value: int, sign_bit: int) -> int:
    mag = value & ((1 << sign_bit) - 1)
    return -mag if (value >> sign_bit) & 1 else mag


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="COM3")
    p.add_argument("--id", type=int, default=5, help="motor id (wrist_roll=5)")
    p.add_argument("--seconds", type=float, default=20.0)
    p.add_argument("--hz", type=float, default=5.0)
    args = p.parse_args()

    import scservo_sdk as scs

    ph = scs.PortHandler(args.port)
    if not ph.openPort():
        raise SystemExit(f"Could not open port {args.port}")
    if not ph.setBaudRate(BAUDRATE):
        raise SystemExit(f"Could not set baudrate {BAUDRATE}")
    pkt = scs.PacketHandler(PROTOCOL)

    model, comm, err = pkt.ping(ph, args.id)
    if comm != scs.COMM_SUCCESS:
        raise SystemExit(f"Motor ID {args.id} did not respond on {args.port}: {pkt.getTxRxResult(comm)}")
    print(f"Motor ID {args.id} responded (model={model}) on {args.port}\n")

    def read(name):
        addr, size = ADDR[name]
        if size == 1:
            val, comm, err = pkt.read1ByteTxRx(ph, args.id, addr)
        else:
            val, comm, err = pkt.read2ByteTxRx(ph, args.id, addr)
        return val if comm == scs.COMM_SUCCESS else None

    overload_torque = read("Overload_Torque")
    max_temp = read("Max_Temperature_Limit")
    print(f"Config -> Overload_Torque limit: {overload_torque}%   Max_Temperature_Limit: {max_temp} C\n")

    period = 1.0 / args.hz
    print(f"{'t(s)':>5} {'load%':>7} {'curr(mA)':>9} {'temp(C)':>7} {'volt(V)':>7} {'torque':>6}  status")
    t0 = time.time()
    worst = {"load": 0.0, "curr": 0, "temp": 0}
    errors_seen = set()
    try:
        while time.time() - t0 < args.seconds:
            raw_load = read("Present_Load")
            raw_curr = read("Present_Current")
            temp = read("Present_Temperature")
            raw_volt = read("Present_Voltage")
            status = read("Status")
            te = read("Torque_Enable")

            load_pct = abs(decode_signed_magnitude(raw_load, 10)) / 10.0 if raw_load is not None else float("nan")
            curr_ma = (raw_curr * 6.5) if raw_curr is not None else float("nan")
            volt = (raw_volt / 10.0) if raw_volt is not None else float("nan")

            flags = []
            if status:
                for bit, name in ERROR_BITS.items():
                    if status & bit:
                        flags.append(name)
                        errors_seen.add(name)
            status_str = ",".join(flags) if flags else "OK"

            worst["load"] = max(worst["load"], load_pct)
            if raw_curr is not None:
                worst["curr"] = max(worst["curr"], curr_ma)
            if temp is not None:
                worst["temp"] = max(worst["temp"], temp)

            print(f"{time.time()-t0:5.1f} {load_pct:7.1f} {curr_ma:9.0f} {temp if temp is not None else -1:7d} "
                  f"{volt:7.1f} {('ON' if te else 'off'):>6}  {status_str}")
            time.sleep(period)
    except KeyboardInterrupt:
        pass
    finally:
        ph.closePort()

    print("\n--- Summary ---")
    print(f"Peak load:        {worst['load']:.1f}%  (overload limit {overload_torque}%)")
    print(f"Peak current:     {worst['curr']:.0f} mA")
    print(f"Peak temperature: {worst['temp']} C  (limit {max_temp} C)")
    if errors_seen:
        print(f"ERROR FLAGS SEEN: {sorted(errors_seen)}")
        if "Overload" in errors_seen or "Overcurrent" in errors_seen:
            print(">> Wrist roll IS hitting overload/overcurrent protection.")
    else:
        print("No hardware error flags raised. No overload detected.")


if __name__ == "__main__":
    main()
