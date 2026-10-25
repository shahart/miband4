"""Load the library without requiring BLE hardware or optional runtime packages."""

import sys
import types


try:
    import bluepy.btle  # noqa: F401
except ImportError:
    bluepy = types.ModuleType("bluepy")
    btle = types.ModuleType("bluepy.btle")

    class Peripheral:
        pass

    class DefaultDelegate:
        def __init__(self):
            pass

    btle.Peripheral = Peripheral
    btle.DefaultDelegate = DefaultDelegate
    btle.ADDR_TYPE_RANDOM = "random"
    btle.ADDR_TYPE_PUBLIC = "public"
    btle.BTLEException = Exception
    bluepy.btle = btle
    sys.modules["bluepy"] = bluepy
    sys.modules["bluepy.btle"] = btle

try:
    from Crypto.Cipher import AES  # noqa: F401
except ImportError:
    crypto = types.ModuleType("Crypto")
    cipher = types.ModuleType("Crypto.Cipher")
    cipher.AES = types.SimpleNamespace(MODE_ECB=1)
    crypto.Cipher = cipher
    sys.modules["Crypto"] = crypto
    sys.modules["Crypto.Cipher"] = cipher
