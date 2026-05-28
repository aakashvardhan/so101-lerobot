#!/usr/bin/env python3
"""Non-destructive scan of a Feetech bus to list which motor IDs respond."""

import argparse

BAUDRATE = 1_000_000
PROTOCOL = 0

EXPECTED = {
    1: "shoulder_pan",
    2: "shoulder_lift",
    3: "elbow_flex",
    4: "wrist_flex",
    5: "wrist_roll",
    6: "gripper",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--max-id", type=int, default=20)
    args = parser.parse_args()

    import scservo_sdk as scs

    ph = scs.PortHandler(args.port)
    if not ph.openPort():
        raise SystemExit(f"Could not open port {args.port}")
    if not ph.setBaudRate(BAUDRATE):
        raise SystemExit(f"Could not set baudrate {BAUDRATE}")
    pkt = scs.PacketHandler(PROTOCOL)

    print(f"\nScanning {args.port} @ {BAUDRATE} baud (IDs 1..{args.max_id})\n")
    found = []
    for id_ in range(1, args.max_id + 1):
        model, comm, err = pkt.ping(ph, id_)
        if comm == scs.COMM_SUCCESS:
            name = EXPECTED.get(id_, "unknown")
            print(f"  ID {id_:>2}  model={model}  ({name})")
            found.append(id_)

    print(f"\nFound IDs: {found}")
    expected_ids = set(EXPECTED.keys())
    missing = sorted(expected_ids - set(found))
    extra = sorted(set(found) - expected_ids)
    if missing:
        print(f"MISSING: {[(i, EXPECTED[i]) for i in missing]}")
    if extra:
        print(f"EXTRA  : {extra}")
    if not missing and not extra:
        print("OK: all expected IDs 1..6 present.")

    ph.closePort()


if __name__ == "__main__":
    main()
