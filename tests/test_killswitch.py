import threading
import time
import unittest

from jevanced.killswitch import KillSwitch


class KillSwitchTest(unittest.TestCase):
    def test_first_reason_wins(self):
        ks = KillSwitch()
        self.assertFalse(ks.tripped)
        ks.trip("first")
        ks.trip("second")
        self.assertTrue(ks.tripped)
        self.assertEqual(ks.reason, "first")
        ks.reset()
        self.assertFalse(ks.tripped)
        self.assertEqual(ks.reason, "")

    def test_wait_returns_early_when_tripped(self):
        ks = KillSwitch()
        threading.Timer(0.05, ks.trip).start()
        started = time.time()
        self.assertTrue(ks.wait(5))
        self.assertLess(time.time() - started, 2)

    def test_wait_times_out(self):
        self.assertFalse(KillSwitch().wait(0.01))
        self.assertFalse(KillSwitch().wait(0))


if __name__ == "__main__":
    unittest.main()
