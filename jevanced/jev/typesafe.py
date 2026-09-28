"""The real Jev client, for Typesafe's System One API.

API reference: https://docs.typesafe.ai/api

- Checking a key is ``GET /v1/models``: 200 means the key works, 401 means
  it doesn't.
- Each decision is one ``POST /v1/systemone`` holding a single Choice
  question over the options built in ``choices``. Jev answers with the
  chosen option, a probability for each option, and a confidence.
- Attacking is the one move that can go badly wrong, so it needs
  ``ATTACK_CONFIDENCE``. Below that, jevanced takes Jev's most likely
  non-attack option instead (bandaging, stepping away or waiting), since
  waiting while in trouble would be worse than either.
- When waiting is the only option, no request is sent at all.
"""

import json

from jevanced.jev import choices
from jevanced.jev.client import (
    JevAuthError,
    JevClient,
    JevResponseError,
    JevUnavailableError,
    KeyCheck,
)
from jevanced.jev.http import default_transport

API_ROOT = "https://api.typesafe.ai/v1"
MODEL = "jev-latest"
QUESTION_ID = "next_action"
ATTACK_CONFIDENCE = 0.5
TIMEOUT_S = 10.0


class TypesafeJevClient(JevClient):
    display_name = "Jev"

    def __init__(self, api_key, transport=None, api_root=API_ROOT):
        self._key = api_key
        self._transport = transport or default_transport()
        self._root = api_root
        self._last_bandage_at = None
        self.last_note = ""

    # ---- JevClient -----------------------------------------------------

    def check_key(self):
        self._call("GET", "/models")
        return KeyCheck(True, "Jev accepted this key.")

    def decide(self, state):
        options = choices.build_options(state, self._last_bandage_at)
        if len(options) == 1:
            self.last_note = "Nothing to decide, waiting."
            return options[0].action
        reply = self._call("POST", "/systemone", {
            "model": MODEL,
            "state": choices.describe_state(state, options),
            "questions": {QUESTION_ID: choices.question(options)},
        })
        choice, probabilities, confidence = self._answer(reply)
        by_key = dict((o.key, o) for o in options)
        if choice not in by_key:
            raise JevResponseError("Jev chose {0!r}, which wasn't offered".format(choice))
        option = by_key[choice]
        if option.action["type"] == "attack" and confidence < ATTACK_CONFIDENCE:
            safe = [o for o in options if o.action["type"] != "attack"]
            option = max(safe, key=lambda o: probabilities.get(o.key, 0.0))
            self.last_note = "Not sure enough to attack (confidence {0:.2f}), so: {1}".format(
                confidence, _short(option))
        else:
            self.last_note = "{0} (confidence {1:.2f})".format(_short(option), confidence)
        if option.key == "bandage_self":
            self._last_bandage_at = state.get("timestamp", 0.0)
        return option.action

    # ---- HTTP ----------------------------------------------------------

    def _call(self, method, path, payload=None):
        headers = {"Authorization": "Bearer " + self._key, "Accept": "application/json"}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload)
        status, text = self._transport.request(method, self._root + path, headers, body, TIMEOUT_S)
        if status in (401, 403):
            raise JevAuthError("the key was refused (HTTP {0})".format(status))
        if status == 429 or status == 529 or status >= 500:
            raise JevUnavailableError("Jev is busy (HTTP {0}); trying again next turn".format(status))
        if status != 200:
            raise JevResponseError("Jev returned HTTP {0}: {1}".format(status, _detail(text)))
        try:
            return json.loads(text)
        except ValueError:
            raise JevResponseError("Jev's reply wasn't JSON")

    @staticmethod
    def _answer(reply):
        try:
            answer = reply["answers"][QUESTION_ID]
            probabilities = dict((str(k), float(v))
                                 for k, v in (answer.get("probabilities") or {}).items())
            return str(answer["choice"]), probabilities, float(answer["confidence"])
        except (AttributeError, KeyError, TypeError, ValueError):
            raise JevResponseError("Jev's reply had no usable answer")


def _short(option):
    """The option's first sentence, for the log."""
    return option.description.split(". ")[0].rstrip(".")


def _detail(text):
    text = (text or "").strip().replace("\n", " ")
    return text[:200] or "no details"
