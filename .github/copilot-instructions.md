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
- **struct.pack()** for binary encoding: `struct.pack('<H', value)` for little-endian shorts
- **Notification responses**: Always check first 3 bytes for command type (e.g., `b'\x10\x01\x01'`)
- **Payload format**: Command byte + data. Example: alarm uses `struct.pack("5B", 2, alarm_tag, hour, minute, mask)`

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
