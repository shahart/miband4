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
1. Call `initialize()` → sends random number request
2. Receives random number in `Delegate.handleNotification()`
3. Encrypt with AES-ECB, send encrypted value
4. Device responds with `AUTH_STATES.AUTH_OK` or error
5. Disable auth notifications before using features

### Data Fetching Pattern (Activity Logs, Heart Rate)
- **Polling-based**: Use `waitForNotifications(timeout)` to block for BLE events
- **Callback pattern**: Pass callback functions (e.g., `heart_measure_callback`) to handlers
- **Queue extraction**: `_get_from_queue(QUEUE_TYPES.XXX)` filters by type; unused items re-queued
- Example: `start_heart_rate_realtime()` loops `waitForNotifications(0.5)` with 12-sec ping

## Project-Specific Patterns

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
- Sequential: send start payload → write firmware in 20-byte chunks → send completion commands
- CRC32 calculated with `zlib` (optional dependency)
- Firmware (.fw) triggers reboot command; watchface (.bin) does not

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
