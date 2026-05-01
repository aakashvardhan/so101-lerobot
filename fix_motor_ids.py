#!/usr/bin/env python3
"""
Standalone script to verify and re-assign IDs 5 (wrist_roll) and 6 (gripper)
on Feetech STS3215 servos, with explicit EEPROM lock/unlock and post-write
verification.

Usage:
    uv run python scripts/fix_motor_ids.py --port /dev/tty.usbserial-XXXX

Find your port with:
    ls /dev/tty.usbserial-*
    ls /dev/tty.usbmodem*
"""

import argparse
import time

BAUDRATE = 1_000_000
PROTOCOL = 0

# STS3215 control table addresses
ADDR_ID = 5
ADDR_BAUD = 6
ADDR_TORQUE = 40
ADDR_LOCK = 55


def build_port(port: str, baudrate: int):
    import scservo_sdk as scs

    ph = scs.PortHandler(port)
    if not ph.openPort():
        raise RuntimeError(f"Could not open port {port}")
    if not ph.setBaudRate(baudrate):
        raise RuntimeError(f"Could not set baudrate {baudrate}")
    return ph


def raw_read(ph, pkt, id_: int, addr: int, length: int) -> int | None:
    import scservo_sdk as scs

    val, comm, err = pkt.read1ByteTxRx(ph, id_, addr)
    if comm != scs.COMM_SUCCESS or err:
        return None
    return val


def raw_write(ph, pkt, id_: int, addr: int, value: int) -> bool:
    import scservo_sdk as scs

    comm, err = pkt.write1ByteTxRx(ph, id_, addr, value)
    return comm == scs.COMM_SUCCESS and not err


def scan_for_single_motor(ph, pkt, expected_id_hint: int | None = None) -> int | None:
    """Broadcast ping to find a single connected motor; returns its current ID."""
    import scservo_sdk as scs

    print("  Scanning bus for any motor (broadcast ping)...")
    found = []
    for id_ in range(1, 20):
        model, comm, err = pkt.ping(ph, id_)
        if comm == scs.COMM_SUCCESS:
            print(f"  Found motor at ID={id_} (model={model})")
            found.append(id_)

    if len(found) == 0:
        print("  ERROR: No motors found. Check wiring and power.")
        return None
    if len(found) > 1:
        print(f"  WARNING: Multiple motors found {found}. Only connect ONE motor at a time!")
        return None
    return found[0]


def assign_id(ph, pkt, current_id: int, target_id: int) -> bool:
    print(f"  Assigning ID {current_id} -> {target_id} ...")

    # 1. Disable torque
    if not raw_write(ph, pkt, current_id, ADDR_TORQUE, 0):
        print("  ERROR: Could not disable torque")
        return False
    time.sleep(0.05)

    # 2. Unlock EEPROM
    if not raw_write(ph, pkt, current_id, ADDR_LOCK, 0):
        print("  ERROR: Could not unlock EEPROM (Lock=0)")
        return False
    time.sleep(0.05)

    # 3. Write new ID
    if not raw_write(ph, pkt, current_id, ADDR_ID, target_id):
        print("  ERROR: Could not write new ID")
        return False
    time.sleep(0.05)

    # 4. Re-lock EEPROM with NEW id (commits the EPROM write)
    if not raw_write(ph, pkt, target_id, ADDR_LOCK, 1):
        print("  WARNING: Could not re-lock EEPROM (Lock=1) — write may not persist")
    time.sleep(0.05)

    # 5. Verify the new ID is live
    import scservo_sdk as scs
    _, comm, _ = pkt.ping(ph, target_id)
    if comm != scs.COMM_SUCCESS:
        print(f"  ERROR: Motor does not respond at new ID {target_id}")
        return False

    print(f"  OK: Motor now responds at ID {target_id}")
    return True


def verify_after_power_cycle(ph, pkt, target_id: int) -> bool:
    print(f"\n  *** POWER CYCLE THE MOTOR NOW (disconnect and reconnect power) ***")
    input("  Then press Enter to verify the ID persisted ...")

    import scservo_sdk as scs
    _, comm, _ = pkt.ping(ph, target_id)
    if comm == scs.COMM_SUCCESS:
        print(f"  VERIFIED: Motor responds at ID {target_id} after power cycle. EPROM write persisted.")
        return True
    else:
        print(f"  FAIL: Motor does NOT respond at ID {target_id} after power cycle.")
        print(f"  The EPROM write did not persist. This usually means:")
        print(f"    1) The servo's EEPROM is worn or faulty — try a replacement servo")
        print(f"    2) Power instability during write — ensure stable 5–7.4V supply")
        print(f"    3) Firmware needs updating (requires Feetech FD tool on Windows/Parallels)")
        return False


def main():
    parser = argparse.ArgumentParser(description="Fix Feetech STS3215 motor IDs for SO-101")
    parser.add_argument("--port", required=True, help="Serial port, e.g. /dev/tty.usbserial-XXXX")
    parser.add_argument(
        "--motors",
        nargs="+",
        default=["wrist_roll:5", "gripper:6"],
        help="Motors to fix as name:target_id pairs (default: wrist_roll:5 gripper:6)",
    )
    args = parser.parse_args()

    try:
        import scservo_sdk as scs
    except ImportError:
        print("ERROR: scservo_sdk not installed. Run: uv sync --extra feetech")
        return

    motor_targets = {}
    for item in args.motors:
        name, id_str = item.split(":")
        motor_targets[name] = int(id_str)

    ph = build_port(args.port, BAUDRATE)
    pkt = scs.PacketHandler(PROTOCOL)

    print(f"\nConnected to {args.port} @ {BAUDRATE} baud\n")

    for name, target_id in motor_targets.items():
        print(f"{'='*60}")
        print(f"Setting up motor: {name} -> ID {target_id}")
        print(f"{'='*60}")
        print(f"Connect ONLY the '{name}' motor to the bus, then press Enter...")
        input()

        current_id = scan_for_single_motor(ph, pkt)
        if current_id is None:
            print(f"Skipping {name} — could not find a single motor.")
            continue

        if current_id == target_id:
            print(f"  Motor is already at ID {target_id}.")
        else:
            ok = assign_id(ph, pkt, current_id, target_id)
            if not ok:
                print(f"  FAILED to assign ID {target_id} to {name}. Check connections.")
                continue

        verify_after_power_cycle(ph, pkt, target_id)

    ph.closePort()
    print("\nDone. All motors processed.")
    print("You can now run: uv run lerobot-calibrate --robot.type=so101_follower ...")


if __name__ == "__main__":
    main()
