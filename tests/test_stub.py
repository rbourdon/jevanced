import unittest

from jevanced import actions
from jevanced.jev.stub import StubJevClient
from tests.fakes import bandage, make_state


class StubTest(unittest.TestCase):
    def test_key_is_never_reported_verified(self):
        self.assertFalse(StubJevClient("k").check_key().verified)

    def test_waits_when_healthy(self):
        action = StubJevClient("k").decide(make_state(hits=90, backpack=[bandage()]).to_dict())
        self.assertEqual(action["type"], "wait")

    def test_bandages_self_when_hurt_then_cools_down(self):
        stub = StubJevClient("k")
        hurt = make_state(hits=30, backpack=[bandage(serial=77)], timestamp=100.0)
        action = stub.decide(hurt.to_dict())
        self.assertEqual(action, {"type": "use_item", "serial": 77, "target": "self"})
        actions.validate(action)
        hurt.timestamp = 103.0
        self.assertEqual(stub.decide(hurt.to_dict())["type"], "wait")
        hurt.timestamp = 111.0
        self.assertEqual(stub.decide(hurt.to_dict())["type"], "use_item")

    def test_waits_when_hurt_without_bandages(self):
        self.assertEqual(StubJevClient("k").decide(make_state(hits=10).to_dict())["type"], "wait")

    def test_never_offensive(self):
        stub = StubJevClient("k")
        for hits in range(0, 101, 5):
            state = make_state(hits=hits, backpack=[bandage()], timestamp=hits * 100.0)
            self.assertIn(stub.decide(state.to_dict())["type"], ("wait", "use_item"))


if __name__ == "__main__":
    unittest.main()
