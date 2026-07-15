"""Verify all joints read within training distribution after calibration patch."""
import sys, json, pathlib, time
sys.path.insert(0, "src")
from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

MOTORS = {
    "shoulder_pan":  Motor(1, "sts3215", MotorNormMode.DEGREES),
    "shoulder_lift": Motor(2, "sts3215", MotorNormMode.DEGREES),
    "elbow_flex":    Motor(3, "sts3215", MotorNormMode.DEGREES),
    "wrist_flex":    Motor(4, "sts3215", MotorNormMode.DEGREES),
    "wrist_roll":    Motor(5, "sts3215", MotorNormMode.DEGREES),
    "gripper":       Motor(6, "sts3215", MotorNormMode.RANGE_0_100),
}
raw = json.loads(pathlib.Path("calibration/robots/so_follower/my_so_arm.json").read_text())
cal = {k: MotorCalibration(**v) for k, v in raw.items()}
bus = None
for attempt in range(8):
    try:
        bus = FeetechMotorsBus(port="COM3", motors=MOTORS, calibration=cal)
        bus.connect()
        break
    except Exception:
        try:
            bus.disconnect()
        except Exception:
            pass
        time.sleep(1.2)
if bus is None or not bus.is_connected:
    print("motor 5 latched - power cycle needed")
    sys.exit(2)

norm = bus.sync_read("Present_Position", normalize=True)
# stats from act_so101_pick_cube_v2 (60k) policy_preprocessor normalizer
train_mean = {"shoulder_pan": -6.5, "shoulder_lift": -38.9, "elbow_flex": 24.5,
              "wrist_flex": 68.8, "wrist_roll": -99.6, "gripper": 22.0}
train_std = {"shoulder_pan": 13.8, "shoulder_lift": 50.0, "elbow_flex": 43.4,
             "wrist_flex": 17.4, "wrist_roll": 14.4, "gripper": 21.2}
print(f"{'joint':16} {'live':>8} {'train_mu':>9} {'sigma_off':>10}")
for j in MOTORS:
    live, mu, sd = norm[j], train_mean[j], train_std[j]
    sig = (live - mu) / sd
    flag = "" if abs(sig) < 3 else "  <-- OOD"
    print(f"{j:16} {live:>8.1f} {mu:>9.1f} {sig:>9.1f}sd{flag}")
bus.disconnect()
