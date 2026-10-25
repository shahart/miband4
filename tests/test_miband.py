import struct
from datetime import datetime
from queue import Queue

from constants import AUTH_STATES, QUEUE_TYPES
from miband import Delegate, miband


def test_create_date_data_round_trips_through_date_parser():
    expected = datetime(2024, 2, 29, 23, 58, 57)

    parsed = miband._parse_date(miband.create_date_data(expected))

    assert parsed["date"] == expected
    assert parsed["day_of_week"] == expected.isoweekday()
    assert parsed["fractions256"] == 0


def test_parse_date_handles_truncated_fields():
    parsed = miband._parse_date(b"\xe8\x07\x02")

    assert parsed["date"] is None
    assert parsed["day_of_week"] is None
    assert parsed["fractions256"] is None


def test_raw_heart_parser_unpacks_seven_unsigned_values():
    packet = b"\x01\x02" + struct.pack("<7H", 1, 2, 3, 255, 1024, 4096, 65535)

    assert miband._parse_raw_heart(None, packet) == (1, 2, 3, 255, 1024, 4096, 65535)


def test_raw_accel_parser_returns_three_axis_samples():
    packet = b"\x00\x00" + struct.pack("<9h", -1, 2, 3, 4, -5, 6, 7, 8, -9)

    assert miband._parse_raw_accel(None, packet) == [
        {"x": -1, "y": 2, "wtf": 3},
        {"x": 4, "y": -5, "wtf": 6},
        {"x": 7, "y": 8, "wtf": -9},
    ]


def test_queue_get_preserves_items_of_other_types():
    band = miband.__new__(miband)
    band.queue = Queue()
    band.queue.put((QUEUE_TYPES.HEART, b"heart"))
    band.queue.put((QUEUE_TYPES.RAW_HEART, b"raw"))

    assert band._get_from_queue(QUEUE_TYPES.RAW_HEART) is None
    assert band._get_from_queue(QUEUE_TYPES.RAW_HEART) == b"raw"
    assert band._get_from_queue(QUEUE_TYPES.HEART) == b"heart"
    assert band._get_from_queue(QUEUE_TYPES.HEART) is None


class FakeCharacteristic:
    def getHandle(self):
        return 7


class FakeDevice:
    def __init__(self):
        self._char_auth = FakeCharacteristic()
        self.state = None
        self.status = None
        self.queue = Queue()


def test_auth_notification_success_sets_auth_state():
    device = FakeDevice()

    Delegate(device).handleNotification(7, b"\x10\x03\x01")

    assert device.state == AUTH_STATES.AUTH_OK


def test_unrecognized_auth_notification_marks_auth_failed():
    device = FakeDevice()

    Delegate(device).handleNotification(7, b"\x00\x00\x00")

    assert device.state == AUTH_STATES.AUTH_FAILED
