import json
import unittest

from jevanced.jev import JevAuthError, JevResponseError, JevUnavailableError, make_client
from jevanced.jev.typesafe import ATTACK_CONFIDENCE, TypesafeJevClient
from tests.test_choices import mob, state

KEY = "ts-test-key-1234"


class FakeTransport(object):
    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def request(self, method, url, headers, body=None, timeout_s=10.0):
        self.requests.append({"method": method, "url": url, "headers": headers,
                              "body": json.loads(body) if body else None})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        status, payload = reply
        return status, payload if isinstance(payload, str) else json.dumps(payload)


def chose(option, confidence=0.9, probabilities=None):
    return 200, {"model": "jev-1.13.0", "usage": {"input_tokens": 300, "output_tokens": 20},
                 "answers": {"next_action": {"type": "choice", "choice": option,
                                             "probabilities": probabilities or {option: confidence},
                                             "confidence": confidence}}}


def client(*replies):
    transport = FakeTransport(*replies)
    return TypesafeJevClient(KEY, transport=transport), transport


class CheckKeyTest(unittest.TestCase):
    def test_accepted_key_is_verified(self):
        c, t = client((200, {"models": [{"name": "jev-latest"}]}))
        self.assertTrue(c.check_key().verified)
        self.assertEqual(t.requests[0]["method"], "GET")
        self.assertEqual(t.requests[0]["url"], "https://api.typesafe.ai/v1/models")
        self.assertEqual(t.requests[0]["headers"]["Authorization"], "Bearer " + KEY)

    def test_refused_key_raises_auth_error(self):
        c, _ = client((401, {"detail": "Invalid API key"}))
        with self.assertRaises(JevAuthError):
            c.check_key()

    def test_busy_and_unreachable_are_retryable(self):
        for reply in ((429, ""), (529, ""), (503, "down"), JevUnavailableError("timeout")):
            c, _ = client(reply)
            with self.assertRaises(JevUnavailableError):
                c.check_key()

    def test_errors_never_carry_the_key(self):
        c, _ = client((422, {"detail": "questions: field required"}))
        with self.assertRaises(JevResponseError) as ctx:
            c.decide(state(hits=50))
        self.assertNotIn(KEY, str(ctx.exception))
        self.assertIn("422", str(ctx.exception))


class DecideTest(unittest.TestCase):
    def test_nothing_to_decide_sends_no_request(self):
        c, t = client()
        self.assertEqual(c.decide(state())["type"], "wait")
        self.assertEqual(t.requests, [])

    def test_sends_one_choice_question_and_returns_its_action(self):
        c, t = client(chose("attack_1"))
        action = c.decide(state(mobiles=[mob(7, 103, 100)]))
        self.assertEqual(action, {"type": "attack", "serial": 7})
        sent = t.requests[0]
        self.assertEqual(sent["url"], "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(sent["body"]["model"], "jev-latest")
        question = sent["body"]["questions"]["next_action"]
        self.assertEqual(question["type"], "choice")
        self.assertEqual(sorted(question["criteria"]), ["attack_1", "step_away", "wait"])
        self.assertIn("confidence 0.90", c.last_note)

    def test_unsure_attack_falls_back_to_the_likeliest_safe_move(self):
        c, _ = client(chose("attack_1", confidence=ATTACK_CONFIDENCE - 0.1, probabilities={
            "attack_1": 0.5, "step_away": 0.3, "bandage_self": 0.15, "wait": 0.05}))
        action = c.decide(state(hits=40, mobiles=[mob(7, 101, 100)]))
        self.assertEqual(action["type"], "walk")
        self.assertIn("Not sure enough to attack", c.last_note)

    def test_unsure_defensive_moves_still_happen(self):
        c, _ = client(chose("bandage_self", confidence=0.2, probabilities={
            "bandage_self": 0.55, "step_away": 0.43, "attack_1": 0.02}))
        action = c.decide(state(hits=12, mobiles=[mob(7, 101, 100)]))
        self.assertEqual(action["type"], "use_item")

    def test_bandage_starts_a_cooldown(self):
        c, t = client(chose("bandage_self"))
        self.assertEqual(c.decide(state(hits=50, timestamp=100.0))["type"], "use_item")
        # Five seconds later bandaging isn't offered, so there's nothing to ask.
        self.assertEqual(c.decide(state(hits=50, timestamp=105.0))["type"], "wait")
        self.assertEqual(len(t.requests), 1)

    def test_unoffered_or_malformed_answers_are_rejected(self):
        for reply in (chose("cast_meteor"), (200, {"answers": {}}), (200, "not json")):
            c, _ = client(reply)
            with self.assertRaises(JevResponseError):
                c.decide(state(hits=50))


class MakeClientTest(unittest.TestCase):
    def test_jev_backend_is_the_typesafe_client(self):
        self.assertIsInstance(make_client("jev", KEY), TypesafeJevClient)


if __name__ == "__main__":
    unittest.main()
