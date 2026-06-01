#!/usr/bin/env python3
"""Re-lock EEPROM for motor IDs 5 and 6 (non-interactive)."""

import argparse
import time

BAUDRATE = 1_000_000


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--ids", type=int, nargs="+", default=[5, 6])
    args = parser.parse_args()

    import scservo_sdk as scs

    ph = scs.PortHandler(args.port)
    if not ph.openPort():
        raise SystemExit(f"Could not open {args.port}")
    if not ph.setBaudRate(BAUDRATE):
        raise SystemExit(f"Could not set baudrate {BAUDRATE}")
    pkt = scs.PacketHandler(0)

    print(f"Burning EEPROM lock for IDs {args.ids} on {args.port}\n")
    for id_ in args.ids:
        pkt.write1ByteTxRx(ph, id_, 40, 0)
        time.sleep(0.05)
        pkt.write1ByteTxRx(ph, id_, 55, 0)
        time.sleep(0.05)
        pkt.write1ByteTxRx(ph, id_, 5, id_)
        time.sleep(0.05)
        pkt.write1ByteTxRx(ph, id_, 55, 1)
        time.sleep(0.05)
        _, comm, _ = pkt.ping(ph, id_)
        status = "OK" if comm == scs.COMM_SUCCESS else "FAILED"
        print(f"  ID {id_}: {status}")

    ph.closePort()
    print("\nDone. Power-cycle the arm if IDs were wrong before.")


if __name__ == "__main__":
    main()
