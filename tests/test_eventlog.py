import unittest

from jevanced.eventlog import REDACTED, EventLog


class EventLogTest(unittest.TestCase):
    def test_redacts_secrets_everywhere(self):
        written = []
        log = EventLog(clock=lambda: 0, sink=written.append)
        log.add_secret("sk-topsecret")
        log.error("request failed with key sk-topsecret!")
        self.assertNotIn("sk-topsecret", log.lines()[-1])
        self.assertIn(REDACTED, log.lines()[-1])
        self.assertNotIn("sk-topsecret", written[-1])

    def test_capacity(self):
        log = EventLog(capacity=3, clock=lambda: 0)
        for i in range(5):
            log.info(str(i))
        self.assertEqual(len(log.lines()), 3)
        self.assertTrue(log.lines()[-1].endswith("4"))
        self.assertEqual(len(log.lines(limit=2)), 2)

    def test_broken_sink_does_not_raise(self):
        def sink(line):
            raise IOError("disk full")
        EventLog(sink=sink).info("hello")


if __name__ == "__main__":
    unittest.main()
