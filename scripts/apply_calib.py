"""Write the patched calibration file to the motor hardware so is_calibrated==True,
then verify wrist_roll reports correctly. No motion is commanded."""
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

print("is_calibrated BEFORE write:", bus.is_calibrated)
bus.write_calibration(cal)
print("is_calibrated AFTER write :", bus.is_calibrated)

# Verify hardware limits and reported angle for wrist_roll
mn = bus.read("Min_Position_Limit", "wrist_roll", normalize=False)
mx = bus.read("Max_Position_Limit", "wrist_roll", normalize=False)
ho = bus.read("Homing_Offset", "wrist_roll", normalize=False)
norm = bus.sync_read("Present_Position", normalize=True)
print(f"wrist_roll HW: Min_Pos={mn} Max_Pos={mx} Homing={ho}")
print(f"wrist_roll normalized = {norm['wrist_roll']:.1f} deg (target ~ -94)")
print("all normalized:", {k: round(v, 1) for k, v in norm.items()})
bus.disconnect()
print("Done.")
