import os
import shutil
import tempfile
import unittest

from jevanced.keystore import KeyFormatError, KeyStore, PlainProtector, mask_key, normalise_key


class XorProtector(object):
    """Stands in for DPAPI in tests."""
    secure = True
    header = b"TESTXOR1\n"

    def protect(self, data):
        return bytes(bytearray(b ^ 0x5A for b in bytearray(data)))

    unprotect = protect


class KeyStoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "sub", "key.bin")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_round_trip(self):
        store = KeyStore(self.path, XorProtector())
        self.assertIsNone(store.load())
        self.assertFalse(store.has_key())
        store.save("  sk-abcdef123456  ")
        self.assertEqual(store.load(), "sk-abcdef123456")
        self.assertTrue(store.encrypted)

    def test_key_is_not_on_disk_in_the_clear(self):
        store = KeyStore(self.path, XorProtector())
        store.save("sk-abcdef123456")
        with open(self.path, "rb") as handle:
            self.assertNotIn(b"sk-abcdef123456", handle.read())

    def test_other_protector_file_reads_as_missing(self):
        KeyStore(self.path, PlainProtector()).save("sk-abcdef123456")
        self.assertIsNone(KeyStore(self.path, XorProtector()).load())

    def test_clear(self):
        store = KeyStore(self.path, XorProtector())
        store.save("sk-abcdef123456")
        store.clear()
        self.assertIsNone(store.load())
        store.clear()  # clearing twice is fine

    def test_plain_protector_is_marked_insecure(self):
        self.assertFalse(KeyStore(self.path, PlainProtector()).encrypted)


class KeyFormatTest(unittest.TestCase):
    def test_rejects_empty_and_spaces(self):
        for bad in [None, "", "   ", "abc def", "abc\ndef"]:
            with self.assertRaises(KeyFormatError):
                normalise_key(bad)

    def test_mask_shows_at_most_last_four(self):
        self.assertEqual(mask_key(""), "")
        self.assertEqual(mask_key("short"), "•" * 8)
        masked = mask_key("sk-verysecretvalue9876")
        self.assertTrue(masked.endswith("9876"))
        self.assertNotIn("secret", masked)


if __name__ == "__main__":
    unittest.main()
