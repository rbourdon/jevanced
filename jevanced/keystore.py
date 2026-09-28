"""Stores the user's Jev API key on their own machine.

On Windows the key is encrypted with DPAPI (CurrentUser scope), so the file
is useless to anyone who copies it off the machine or to another Windows
account. Where DPAPI isn't available the key is stored unencrypted and the
UI says so. The key is never logged and only ever shown masked.
"""

import os

KEY_FILE_NAME = "jev_key.bin"
_ENTROPY = b"jevanced/jev-api-key/v1"
_PLAIN_HEADER = b"JEVPLAIN1\n"
_DPAPI_HEADER = b"JEVDPAPI1\n"


class KeyFormatError(ValueError):
    pass


def normalise_key(raw):
    """Trim the pasted key and reject obviously broken input.

    Jev's real key format isn't documented yet, so this only rejects empty
    keys and keys with spaces or line breaks inside them (a common paste
    mistake). Whether Jev accepts the key is checked against Jev itself.
    """
    if raw is None:
        raise KeyFormatError("Enter your Jev API key.")
    key = str(raw).strip()
    if not key:
        raise KeyFormatError("Enter your Jev API key.")
    for ch in key:
        if ch.isspace():
            raise KeyFormatError("The key has a space or line break in it. Paste it again.")
    if len(key) > 512:
        raise KeyFormatError("That key is too long to be an API key.")
    return key


def mask_key(key):
    """Show at most the last four characters."""
    if not key:
        return ""
    if len(key) < 12:
        return "•" * 8
    return "•" * 8 + key[-4:]


class PlainProtector(object):
    """No encryption. Used only where DPAPI isn't available."""
    secure = False
    header = _PLAIN_HEADER

    def protect(self, data):
        return data

    def unprotect(self, data):
        return data


class DpapiProtector(object):
    """Windows DPAPI via .NET's ProtectedData, for IronPython."""
    secure = True
    header = _DPAPI_HEADER

    def __init__(self):
        import clr  # noqa: F401  (IronPython only)
        try:
            clr.AddReference("System.Security")
        except Exception:
            clr.AddReference("System.Security.Cryptography.ProtectedData")
        from System.Security.Cryptography import DataProtectionScope, ProtectedData
        self._protected_data = ProtectedData
        self._scope = DataProtectionScope.CurrentUser

    @staticmethod
    def _to_net(data):
        from System import Array, Byte
        return Array[Byte](list(bytearray(data)))

    @staticmethod
    def _from_net(array):
        return bytes(bytearray([int(b) for b in array]))

    def protect(self, data):
        result = self._protected_data.Protect(
            self._to_net(data), self._to_net(_ENTROPY), self._scope)
        return self._from_net(result)

    def unprotect(self, data):
        result = self._protected_data.Unprotect(
            self._to_net(data), self._to_net(_ENTROPY), self._scope)
        return self._from_net(result)


def best_protector():
    try:
        protector = DpapiProtector()
        # ProtectedData can import fine and still throw on non-Windows .NET.
        if protector.unprotect(protector.protect(b"probe")) == b"probe":
            return protector
    except Exception:
        pass
    return PlainProtector()


class KeyStore(object):
    def __init__(self, path, protector=None):
        self.path = path
        self.protector = protector if protector is not None else best_protector()

    @property
    def encrypted(self):
        return bool(self.protector.secure)

    def has_key(self):
        return self.load() is not None

    def save(self, raw_key):
        key = normalise_key(raw_key)
        payload = self.protector.header + self.protector.protect(key.encode("utf-8"))
        folder = os.path.dirname(self.path)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        tmp = self.path + ".tmp"
        with open(tmp, "wb") as handle:
            handle.write(payload)
        if os.path.exists(self.path):
            os.remove(self.path)
        os.rename(tmp, self.path)
        return key

    def load(self):
        """Return the stored key, or None if there isn't a readable one."""
        try:
            with open(self.path, "rb") as handle:
                payload = handle.read()
        except (IOError, OSError):
            return None
        header = self.protector.header
        if not payload.startswith(header):
            # Written by a different protector (e.g. copied from another
            # machine); treat as missing so the user re-enters it.
            return None
        try:
            key = self.protector.unprotect(payload[len(header):]).decode("utf-8")
        except Exception:
            return None
        return key or None

    def clear(self):
        try:
            os.remove(self.path)
        except (IOError, OSError):
            pass
