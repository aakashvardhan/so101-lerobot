# Short Troubleshooting Note — Gripper Motor ID Revert

**Issue:** Gripper (ID 6) and wrist_roll (ID 5) revert to ID 5 after power cycle  
**Affected hardware:** Feetech STS3215 servos on SO-101 follower and leader arms  
**Status:** Fixed and verified (both arms)

---

## Symptom

After reboot or power cycle:

- Calibration or teleop fails with `Missing motor IDs: 5, 6`
- `scan_motor_ids.py` shows only IDs 1–4, or ID 5 appears twice
- Wrist_roll and gripper both respond as ID 5 → **bus collision** — neither 5 nor 6 is reliably detected

On the **leader arm**, the same issue affects the trigger (motor 6, named `gripper` in code).

---

## Root Cause

STS3215 servos store motor ID in **EPROM** (non-volatile memory). To write EPROM:

1. Set **Lock = 0** (unlock EEPROM)
2. Write new ID
3. Set **Lock = 1** (commit write to non-volatile storage)

**Stock LeRobot `setup_motor()` did steps 1–2 but skipped step 3.** On some STS3215 firmware batches, the ID change appears to succeed immediately (motor responds at new ID), but after power cycle the old EPROM value (ID 5) is read back. The gripper's EPROM still held ID 5 from a prior partial setup.

---

## Fix Applied

### 1. Code patch (`motors_bus.py`)

After writing ID and baud rate, the code now writes `Lock=1`:

```
Disable torque → Lock=0 → Write ID → Write baud → Lock=1 → verify
```

File: `src/lerobot/motors/motors_bus.py` (lines ~630–635)

### 2. Standalone fix script (`fix_motor_ids.py`)

Interactive script that:

- Connects **one motor at a time**
- Unlocks EEPROM → writes target ID → re-locks EEPROM
- Prompts for **power cycle** to verify persistence

```powershell
python fix_motor_ids.py --port COM3   # follower
python fix_motor_ids.py --port COM4   # leader
```

### 3. Manual one-motor fix (gripper only)

When only the gripper is connected and shows ID 5:

```powershell
python -c "
import time, scservo_sdk as scs
ph = scs.PortHandler('COM3')   # change port
ph.openPort(); ph.setBaudRate(1_000_000)
pkt = scs.PacketHandler(0)
pkt.write1ByteTxRx(ph, 5, 40, 0); time.sleep(0.05)   # torque off
pkt.write1ByteTxRx(ph, 5, 55, 0); time.sleep(0.05)   # Lock=0 unlock
pkt.write1ByteTxRx(ph, 5,  5, 6); time.sleep(0.05)   # write ID=6
pkt.write1ByteTxRx(ph, 6, 55, 1); time.sleep(0.05)   # Lock=1 commit
_, comm, _ = pkt.ping(ph, 6)
print('OK - ID is now 6' if comm == scs.COMM_SUCCESS else 'FAILED')
ph.closePort()
"
```

Then **power-cycle the gripper motor** (unplug power 3 sec, replug) and ping again at ID 6.

### 4. Re-burn IDs 5 and 6 (all motors connected)

After individual fixes, rewrite both IDs with proper EEPROM commit:

```powershell
python -c "
import time, scservo_sdk as scs
ph = scs.PortHandler('COM3')
ph.openPort(); ph.setBaudRate(1_000_000)
pkt = scs.PacketHandler(0)
for target_id in [5, 6]:
    pkt.write1ByteTxRx(ph, target_id, 40, 0); time.sleep(0.05)
    pkt.write1ByteTxRx(ph, target_id, 55, 0); time.sleep(0.05)
    pkt.write1ByteTxRx(ph, target_id,  5, target_id); time.sleep(0.05)
    pkt.write1ByteTxRx(ph, target_id, 55, 1); time.sleep(0.05)
    _, comm, _ = pkt.ping(ph, target_id)
    print(f'ID={target_id}:', 'BURNED IN' if comm == scs.COMM_SUCCESS else 'FAILED')
ph.closePort()
"
```

---

## How We Verified the Fix

| Step | Action | Result |
|------|--------|--------|
| 1 | Connect gripper alone; scan bus | Found at ID 5 (wrong) |
| 2 | Manual ID write 5→6 with Lock=1 | Live ping at ID 6: OK |
| 3 | Power-cycle gripper only | Ping at ID 6 after reboot: **BURNED IN** |
| 4 | Reconnect full arm; scan all IDs | IDs 1–6 all present |
| 5 | `lerobot-calibrate` follower | Connected to all 6 motors, calibration saved |
| 6 | Repeat fix on leader trigger (ID 6) | Same power-cycle test passed |
| 7 | `lerobot-calibrate` leader | All 6 motors OK |
| 8 | `lerobot-teleoperate` both arms | Follower mirrors leader at ~60 Hz, gripper + wrist_roll working |
| 9 | Full arm power cycle + re-calibrate | No `Missing motor IDs` error |

**Definitive test:** ID survives a **cold power cycle** after `Lock=1`. If it does, the EPROM write committed permanently.

---

## Diagnosis Tips (future)

| Observation | Likely cause |
|-------------|--------------|
| IDs 5 and 6 both missing | Bus collision — both at ID 5 |
| Disconnect wrist_roll only → ID 5 appears alone | Gripper reverted from 6 → 5 |
| ID correct live but wrong after reboot | EEPROM not committed — re-run fix with Lock=1 |
| Still reverts after fix | Worn EEPROM, unstable power, or bad firmware — try Feetech FD tool or replace servo |

**Scan command:**

```powershell
python scan_motor_ids.py --port COM3
```

---

## If Fix Still Fails

1. Ensure stable 5–7.4 V power during write
2. Re-run `fix_motor_ids.py` with one motor at a time
3. Update firmware with **Feetech FD** tool (Windows)
4. Replace the servo if EEPROM is worn

---

## Related Docs

- Full setup guide: `environment-setup-reproduction-guide-v0.1.md`
- Windows quick start: `README.md`
- Extended reference: `so-arm-guide.md`
