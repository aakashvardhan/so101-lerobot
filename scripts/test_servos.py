"""
Servo diagnostic: connects to SO-101 follower, reads live register values
for all 6 motors, and checks for signs of oscillation/instability.
Run with: python scripts/test_servos.py
"""
import time
import sys

sys.path.insert(0, "src")

from lerobot.motors import MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus, OperatingMode
from lerobot.motors import Motor

PORT = "COM3"
MOTORS = {
    "shoulder_pan":  Motor(1, "sts3215", MotorNormMode.DEGREES),
    "shoulder_lift": Motor(2, "sts3215", MotorNormMode.DEGREES),
    "elbow_flex":    Motor(3, "sts3215", MotorNormMode.DEGREES),
    "wrist_flex":    Motor(4, "sts3215", MotorNormMode.DEGREES),
    "wrist_roll":    Motor(5, "sts3215", MotorNormMode.DEGREES),
    "gripper":       Motor(6, "sts3215", MotorNormMode.RANGE_0_100),
}

import json, pathlib
CAL_FILE = pathlib.Path("calibration/robots/so_follower/my_so_arm.json")
calibration = None
if CAL_FILE.exists():
    raw = json.loads(CAL_FILE.read_text())
    calibration = {k: MotorCalibration(**v) for k, v in raw.items()}
    print(f"Loaded calibration from {CAL_FILE}")
else:
    print(f"WARNING: No calibration file at {CAL_FILE}")

bus = FeetechMotorsBus(port=PORT, motors=MOTORS, calibration=calibration)
bus.connect()

print("\n=== REGISTER DUMP (all motors) ===")
registers = [
    "P_Coefficient", "I_Coefficient", "D_Coefficient",
    "Maximum_Acceleration", "Moving_Threshold",
    "Max_Torque_Limit", "Protection_Current", "Overload_Torque",
]
for reg in registers:
    try:
        vals = {m: bus.read(reg, m) for m in bus.motors}
        print(f"  {reg:<28}: {vals}")
    except Exception as e:
        print(f"  {reg:<28}: ERROR - {e}")

print("\n=== LIVE POSITION POLL (5 seconds, 20 Hz) ===")
print(f"{'t(s)':>5}  {'pan':>7} {'lift':>7} {'elbow':>7} {'wrist_f':>7} {'wrist_r':>7} {'grip':>7}")
t0 = time.perf_counter()
prev = None
jitter_counts = {m: 0 for m in bus.motors}
samples = 0
try:
    while time.perf_counter() - t0 < 5.0:
        loop_t = time.perf_counter()
        pos = bus.sync_read("Present_Position")
        t = time.perf_counter() - t0
        vals = list(pos.values())
        print(f"{t:>5.2f}  " + "  ".join(f"{v:>7.1f}" for v in vals))
        if prev is not None:
            for m in bus.motors:
                diff = abs(pos[m] - prev[m])
                if diff > 2.0:  # >2 degree jump between polls = jitter
                    jitter_counts[m] += 1
        prev = pos
        samples += 1
        elapsed = time.perf_counter() - loop_t
        time.sleep(max(0, 0.05 - elapsed))
except KeyboardInterrupt:
    pass

print(f"\n=== JITTER SUMMARY ({samples} samples) ===")
for m, count in jitter_counts.items():
    pct = 100 * count / max(samples - 1, 1)
    flag = " <-- UNSTABLE" if pct > 10 else ""
    print(f"  {m:<20}: {count:>3} jumps >2deg ({pct:.1f}%){flag}")

print("\n=== MOVING STATUS (is any motor still moving?) ===")
for m in bus.motors:
    try:
        moving = bus.read("Moving", m)
        load   = bus.read("Present_Load", m)
        print(f"  {m:<20}: moving={moving}  load={load}")
    except Exception as e:
        print(f"  {m:<20}: ERROR - {e}")

bus.disconnect()
print("\nDone.")
