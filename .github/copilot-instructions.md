# MiBand 4 Python Library - AI Agent Guidelines

## Project Overview
This is a Python library for interacting with Xiaomi Mi Band 4 via Bluetooth Low Energy (BLE). It provides features like retrieving health data (heart rate, steps, calories), sending notifications, and updating firmware/watchface. **Runs only on Linux** with bluepy library.

## Architecture & Key Components

### Core Module: `miband.py`
- **Main class**: `miband(Peripheral)` — extends bluepy's BLE peripheral for Mi Band 4 communication
- **Authentication**: Uses AES-ECB encryption with auth keys retrieved from MiFit app database. Features requiring auth are marked in console
- **Notification system**: Custom `Delegate(DefaultDelegate)` class handles BLE notifications for:
  - Authentication handshakes (`_char_auth`)
  - Heart rate data (`_char_heart_measure`)
  - Raw sensor data (accelerometer at handle 0x38)
  - Activity fetch/data streaming (`_char_fetch`, `_char_activity`)
  - Music controls and lost device events (handle 74)
- **Chunked transfer**: Music/watchface data sent via `writeChunked()` in 17-byte chunks with flags (0x80=end, 0x40=start)
- **Queue-based buffering**: `Queue` stores notifications during async operations (heart rate, activity logs)

### Constants: `constants.py`
- **UUIDS class**: Defines all BLE service/characteristic UUIDs (immutable via metaclass)
- **State/type enums**: `AUTH_STATES`, `ALERT_TYPES`, `QUEUE_TYPES`, `MUSICSTATE`, `Weekdays` (all immutable)

### Console Interface: `miband4_console.py`
- Curses-based menu system for interactive testing
- Loads MAC address from `mac.txt`, auth key from `auth_key.txt` (hex format, 32 chars)
- Features requiring auth marked with `@`
- All menu functions include error handling for `BTLEDisconnectError`

### Quick Utility: `quick_call.py`
- Minimal example: sends missed call alert (type 3) to band with phone number

## Critical Workflows

### Setup & Connection
```bash
# Linux only: install libglib2.0-dev
sudo apt-get install libglib2.0-dev
pip3 install -r requirements.txt

# Run console with MAC address
python3 miband4_console.py -m A1:C2:3D:4E:F5:6A

# Or use auth key (hex format)
python3 miband4_console.py -m <MAC> -k <32-char-hex-key>
```

### Authentication Flow (with auth key)

**Sequence Diagram:**
```
Library                          Mi Band 4                    Delegate
  |                                 |                            |
  |------ initialize() ------------>|                            |
  |                                 |                            |
  |--- _req_rdn() (0x02,0x00)------>|                            |
  |                                 |                            |
  |<-- b'\x10\x02\x01' + 16bytes---|-- handleNotification() --->|
  |                 (random number)  |<-- _send_enc_rdn() -------|
  |                                 |                            |
  |--- encrypt + send (0x03,0x00)-->|                            |
  |                                 |                            |
  |<-- b'\x10\x03\x01' (AUTH_OK) ---|-- state=AUTH_OK ---------->|
  |                                 |                            |
  |--- _auth_notif(False) --------->|                            |
  |     (disable notifications)      |                            |
```

**State Machine:**
```
[START] 
  ↓
initialize() → _req_rdn() 
  ↓
waitForNotifications() → receive b'\x10\x02\x01'
  ↓
_send_enc_rdn(random) with AES-ECB
  ↓
waitForNotifications() → receive b'\x10\x03\x01'
  ↓
state = AUTH_STATES.AUTH_OK → return True
  ↓
_auth_notif(False) [disable auth notifications]
  ↓
[READY for auth-required features]

Error paths:
- b'\x10\x01\x04' → AUTH_STATES.KEY_SENDING_FAILED
- b'\x10\x02\x04' → AUTH_STATES.REQUEST_RN_ERROR
- b'\x10\x03\x04' → AUTH_STATES.ENCRIPTION_KEY_FAILED → retry _send_key()
- Timeout → AUTH_STATES.AUTH_FAILED
```

**Implementation:**
1. Call `initialize()` → sends random number request
2. Receives random number in `Delegate.handleNotification()`
3. Encrypt with AES-ECB, send encrypted value
4. Device responds with `AUTH_STATES.AUTH_OK` or error
5. Disable auth notifications before using features

### Data Fetching Pattern (Activity Logs, Heart Rate)

**Heart Rate Realtime Flow:**
```
start_heart_rate_realtime(callback)
  ↓
[Initialize]
- Enable heart_measure descriptor notifications
- Send control: b'\x15\x02\x00' (stop manual)
- Send control: b'\x15\x01\x00' (stop continuous)
- Send control: b'\x15\x01\x01' (start continuous)
  ↓
[Main Loop - every 0.5s]
waitForNotifications(0.5)
  ↓
Delegate receives on handle=_char_heart_measure
  → queue.put((QUEUE_TYPES.HEART, data))
  ↓
_parse_queue()
  → heart_measure_callback(struct.unpack('bb', data)[1])
  ↓
[Keep-alive - every 12s]
Send ping: b'\x16'
  ↓
[Until stop_realtime() called]
- Disable notifications
- Send b'\x15\x01\x00' (stop monitoring)
- Clear callbacks
```

**Activity Log Fetch Flow:**
```
get_activity_betwn_intervals(start_ts, end_ts, callback)
  ↓
start_get_previews_data(start_timestamp)
  ↓
[Enable notifications]
- _auth_previews_data_notif(True)
- Enable _char_fetch and _char_activity descriptors
  ↓
[Trigger data fetch]
Send timestamp packet on _char_fetch
  ↓
Delegate receives b'\x10\x01\x01' on _char_fetch
  → Extract first_timestamp from response
  → Send b'\x02' (acknowledge)
  ↓
Delegate receives activity data on _char_activity (4-byte chunks)
  → Parse: [category, intensity, steps, heart_rate]
  → Increment timestamp by 1 minute
  → If timestamp < end_timestamp: call callback(ts, c, i, s, h)
  ↓
Delegate receives b'\x10\x02\x01' on _char_fetch
  → If more data needed: trigger next interval
  → Else: finish
  ↓
[Disable notifications when done]
_auth_previews_data_notif(False)
```

**Queue-based Data Buffering:**
- **Polling-based**: Use `waitForNotifications(timeout)` to block for BLE events
- **Callback pattern**: Pass callback functions (e.g., `heart_measure_callback`) to handlers
- **Queue extraction**: `_get_from_queue(QUEUE_TYPES.XXX)` filters by type; unused items re-queued
- **Thread-safe**: `Queue` from `queue` module (Python 3) handles concurrent access
- Example: `start_heart_rate_realtime()` loops `waitForNotifications(0.5)` with 12-sec ping

## Project-Specific Patterns

### Delegate Notification Routing

**BLE Event Handler Architecture:**
```
Delegate.handleNotification(hnd, data)
  ↓
[Route by handle]
  ├─ _char_auth.getHandle() → Parse auth state
  │   ├─ b'\x10\x01\x01' → _req_rdn()
  │   ├─ b'\x10\x02\x01' → _send_enc_rdn(random_nr)
  │   ├─ b'\x10\x03\x01' → state = AUTH_OK
  │   └─ b'\x10\x03\x04' → state = ENCRIPTION_KEY_FAILED → retry
  │
  ├─ _char_heart_measure.getHandle() → queue.put((QUEUE_TYPES.HEART, data))
  │
  ├─ Handle 0x38 → Raw sensor data
  │   ├─ 20 bytes, data[0]==1 → queue.put((QUEUE_TYPES.RAW_ACCEL, data))
  │   └─ 16 bytes → queue.put((QUEUE_TYPES.RAW_HEART, data))
  │
  ├─ _char_fetch.getHandle() → Activity control flow
  │   ├─ b'\x10\x01\x01' → Extract timestamp, send b'\x02' ACK
  │   ├─ b'\x10\x02\x01' → Request next interval or finish
  │   └─ b'\x10\x02\x04' → No more data available
  │
  ├─ _char_activity.getHandle() → Parse 4-byte activity records
  │   └─ [category, intensity, steps, heart_rate] per record
  │
  └─ Handle 74 → Music & lost device commands
      ├─ 0x08 → Start ringing (writeDisplayCommand([0x14, 0x00, 0x00]))
      ├─ 0x0f → Stop ringing (writeDisplayCommand([0x14, 0x00, 0x01]))
      ├─ 0xe0 → Music focus in (call _default_music_focus_in())
      ├─ 0xe1 → Music focus out
      ├─ 0x00 → Play
      ├─ 0x01 → Pause
      ├─ 0x03 → Forward
      ├─ 0x04 → Backward
      ├─ 0x05 → Volume up
      └─ 0x06 → Volume down
```

**Queue Processing Pattern:**
```
[During long operations]
Delegate receives data → queue.put((type, data))
  ↓
Main loop: waitForNotifications(0.5)
  ↓
_parse_queue() extracts all queued items by type
  ↓
For each matched type:
  - QUEUE_TYPES.HEART → call heart_measure_callback()
  - QUEUE_TYPES.RAW_HEART → call heart_raw_callback()
  - QUEUE_TYPES.RAW_ACCEL → call accel_raw_callback()
  ↓
Non-matching items → re-queued for next cycle
```

### Byte Protocol Encoding

**Basic Patterns:**
- **struct.pack()** for binary encoding: `struct.pack('<H', value)` for little-endian shorts
- **Notification responses**: Always check first 3 bytes for command type (e.g., `b'\x10\x01\x01'`)
- **Payload format**: Command byte + data

**Real Examples from Codebase:**

1. **Authentication sequence** (3-byte command prefix):
```python
# Delegate checks these command types:
if data[:3] == b'\x10\x01\x01':  # Random number request
    self.device._req_rdn()
elif data[:3] == b'\x10\x02\x01':  # Random number response
    random_nr = data[3:]  # Extract 16-byte random number
    self.device._send_enc_rdn(random_nr)
elif data[:3] == b'\x10\x03\x01':  # Auth success
    self.device.state = AUTH_STATES.AUTH_OK
```

2. **Alarm setting** (command structure):
```python
# Format: command_id, alarm_tag, hour, minute, repetition_mask
alarm_tag = alarm_id
if enabled:
    alarm_tag |= 0x80  # Set enabled bit
    if not snooze:
        alarm_tag |= 0x40  # Set no-snooze bit

repetition_mask = 0x00
for day in days:  # Accumulate day bits (monday=0x01, tuesday=0x02, etc.)
    repetition_mask |= day

packet = struct.pack("5B", 2, alarm_tag, hour, minute, repetition_mask)
char.write(packet)
```

3. **Heart rate control** (command sequences):
```python
# Stop continuous heart monitoring
char_ctrl.write(b'\x15\x01\x00', True)
# Stop manual heart monitoring
char_ctrl.write(b'\x15\x02\x00', True)
# Start manual heart monitoring
char_ctrl.write(b'\x15\x02\x01', True)
# Ping every 12 seconds to keep stream active
char_ctrl.write(b'\x16', True)
```

4. **Chunked transfer** (firmware/watchface):
```python
# Split large data into 17-byte chunks with flags
MAX_CHUNKLENGTH = 17
flag = 0
if remaining <= MAX_CHUNKLENGTH:
    flag |= 0x80  # End-of-transfer flag
    if count == 0:
        flag |= 0x40  # Start flag (first chunk)
elif count > 0:
    flag |= 0x40  # Start flag for middle chunks

chunk = b'\x00' + bytes([flag|type]) + bytes([count & 0xff]) + data_segment
self._char_chunked.write(chunk)
```

5. **Activity fetch trigger** (timestamp format):
```python
# Build timestamp from datetime object (5-byte format)
year = struct.pack("<H", start_timestamp.year)  # 2-byte little-endian
month = struct.pack("b", start_timestamp.month)  # 1-byte signed
day = struct.pack("b", start_timestamp.day)
hour = struct.pack("b", start_timestamp.hour)
minute = struct.pack("b", start_timestamp.minute)
ts = year + month + day + hour + minute  # Total 7 bytes
trigger = b'\x01\x01' + ts + utc_offset  # Command prefix + timestamp + offset
self._char_fetch.write(trigger, False)
```

6. **Battery info parsing** (response structure):
```python
# Response layout: [status_byte, level, charging_status, ..., timestamp_bytes, ...]
level = struct.unpack('b', bytes[1:2])[0]  # Byte 1: battery level
status = 'charging' if struct.unpack('b', bytes[2:3])[0] != 0x0 else 'normal'
datetime_last_off = _parse_date(bytes[3:10])  # Bytes 3-9: off timestamp
datetime_last_charge = _parse_date(bytes[11:18])  # Bytes 11-17: charge timestamp
```

### Callback Registration
Methods use mutable callback slots (e.g., `_default_music_play`) initialized in `init_empty_callbacks()`. Register via:
- `setMusicCallback()` — music controls and focus
- `setLostDeviceCallback()` — find device functionality
- Callbacks stored as instance variables, called from `Delegate` notification handlers

### Notification Descriptor Writes
Enable/disable BLE notifications via descriptors (always UUID 0x2902):
```python
descriptor.write(b"\x01\x00", True)  # enable
descriptor.write(b"\x00\x00", True)  # disable
```

### DFU (Device Firmware Update)

**Firmware/Watchface Update Flow:**
```
dfuUpdate(fileName)
  ↓
[Preparation]
- Calculate CRC32 checksum: zlib.crc32(file)
- Get file size: os.path.getsize()
- Detect type: .fw (firmware) or .bin (watchface)
  ↓
[Send Start Payload]
Send on _char_firmware:
  b'\x01\x08' + 3-byte little-endian size + b'\x00' + 4-byte CRC32
  → Device acknowledges with b'\x03\x01'
  ↓
[Send Data]
Loop: Read file in 20-byte chunks
  → Write each chunk to _char_firmware_write
  → Device may throttle; handle BTLEException gracefully
  ↓
[Finalization]
- Send: b'\x00' (data complete)
- waitForNotifications(2)
- Send: b'\x04' (checksum validation)
- waitForNotifications(2)
- If .fw extension: Send b'\x05' (reboot)
- If .bin extension: Skip reboot (device handles internally)
  ↓
[Result]
.fw files → Device reboots; connection lost
.bin files → Device updates watchface; stays connected
```

**Key Implementation Details:**
- Sequential: send start payload → write firmware in 20-byte chunks → send completion commands
- CRC32 calculated with `zlib` (optional dependency)
- Firmware (.fw) triggers reboot command; watchface (.bin) does not
- **⚠️ WARNING**: `dfuUpdate()` can hard-brick device; only use with official firmware files
- File must be binary format (read with `"rb"` mode)

### Data Parsing Helpers
- `_parse_date()` — handles 9-byte timestamp (year, month, day, hour, minute, second, weekday, fractions)
- `_parse_raw_heart()` — unpacks 16 bytes into 7 heart rate samples
- `_parse_raw_accel()` — unpacks 20 bytes into 3 x,y,z acceleration tuples
- `_parse_battery_response()` — extracts level, status, charge/off timestamps

## Dependencies & Environment

- **bluepy**: BLE communication (Linux only, requires libglib2.0-dev)
- **pycrypto**: AES encryption for auth
- **curses-menu**: Interactive console UI
- **zlib**: Optional, required only for firmware updates

## Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| "Auth failed" | Ensure `auth_key.txt` has 32-char hex key from MiFit database; hard reset invalidates key |
| BLE disconnect | Retry with exponential backoff; ensure Bluetooth is off on paired phone |
| Notification timeout | Verify descriptor write enabled notifications; some commands need `withResponse=True` |
| Firmware brick risk | `dfuUpdate()` can hard-brick device; only use with official firmware files |

## Testing & Quality
- Python 3.10+ with flake8 (max-line-length=127, max-complexity=10)
- No pytest tests in repository — features validated via console menu
- GitHub Actions runs flake8 lint checks on push/PR

## When Extending
- Reverse-engineer new BLE commands from Gadgetbridge project or snooped ACL packets
- Add new UUIDs to `constants.py` UUIDS class
- Handle notifications in `Delegate.handleNotification()` — parse first 3 bytes for command type
- Use existing callback pattern for async events
- Test with actual device before merging (no test suite)
