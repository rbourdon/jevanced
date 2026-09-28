"""The actions jevanced will carry out, and validation of what Jev asks for.

Jev's reply is untrusted input: anything that doesn't match one of these
shapes exactly is rejected before it reaches the game.

Action shapes (dicts):

    {"type": "wait", "ms": 1000}
    {"type": "walk", "direction": "North"}
    {"type": "move_to", "x": 1, "y": 2, "z": 0}
    {"type": "use_skill", "skill": "Hiding", "target": "self" | 1234}
    {"type": "cast", "spell": "Greater Heal", "target": "self" | 1234}
    {"type": "use_item", "serial": 1234, "target": "self" | 1234 | TILE}
    {"type": "equip", "serial": 1234}
    {"type": "war_mode", "on": true}
    {"type": "say", "text": "hello"}
    {"type": "stop", "reason": "done"}

"target" is optional wherever it appears. TILE is a map tile such as a
tree: {"x": 1, "y": 2, "z": 0, "tile": 3274}.

There is deliberately no attack action: jevanced doesn't start fights.
"""

import re

DIRECTIONS = ("North", "Right", "East", "Down", "South", "Left", "West", "Up")

ALL_ACTION_TYPES = ("wait", "walk", "move_to", "use_skill", "cast",
                    "use_item", "equip", "war_mode", "say", "stop")

# Speech is off by default: it puts model-written text in front of other
# players, so the user opts in from the UI.
DEFAULT_ALLOWED = tuple(t for t in ALL_ACTION_TYPES if t != "say")

MAX_WAIT_MS = 10000
MAX_SAY_LENGTH = 120
MAX_COORD = 7168  # widest UO map
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z' ]{0,39}$")


class InvalidAction(ValueError):
    pass


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _serial(action, key):
    value = action.get(key)
    if not _is_int(value) or value <= 0:
        raise InvalidAction("'{0}' must be a positive integer serial".format(key))
    return value


def _target(action):
    if "target" not in action or action["target"] is None:
        return None
    value = action["target"]
    if value == "self":
        return "self"
    if _is_int(value) and value > 0:
        return value
    if isinstance(value, dict):
        return {
            "x": _coord(value, "x", 0, MAX_COORD),
            "y": _coord(value, "y", 0, MAX_COORD),
            "z": _coord(value, "z", -128, 127),
            "tile": _coord(value, "tile", 1, 0xFFFF),
        }
    raise InvalidAction("'target' must be \"self\", a positive integer serial or a map tile")


def _name(action, key):
    value = action.get(key)
    if not isinstance(value, str) or not _NAME_RE.match(value):
        raise InvalidAction("'{0}' must be a plain name of up to 40 letters".format(key))
    return value


def _coord(action, key, low, high):
    value = action.get(key)
    if not _is_int(value) or value < low or value > high:
        raise InvalidAction("'{0}' must be an integer from {1} to {2}".format(key, low, high))
    return value


def validate(action, allowed=DEFAULT_ALLOWED):
    """Return a clean copy of ``action`` or raise InvalidAction."""
    if not isinstance(action, dict):
        raise InvalidAction("action must be an object")
    kind = action.get("type")
    if kind not in ALL_ACTION_TYPES:
        raise InvalidAction("unknown action type {0!r}".format(kind))
    if kind not in allowed:
        raise InvalidAction("action type '{0}' is turned off".format(kind))

    if kind == "wait":
        ms = action.get("ms", 1000)
        if not _is_int(ms) or ms < 0 or ms > MAX_WAIT_MS:
            raise InvalidAction("'ms' must be an integer from 0 to {0}".format(MAX_WAIT_MS))
        return {"type": "wait", "ms": ms}
    if kind == "walk":
        direction = action.get("direction")
        if direction not in DIRECTIONS:
            raise InvalidAction("'direction' must be one of " + ", ".join(DIRECTIONS))
        return {"type": "walk", "direction": direction}
    if kind == "move_to":
        return {
            "type": "move_to",
            "x": _coord(action, "x", 0, MAX_COORD),
            "y": _coord(action, "y", 0, MAX_COORD),
            "z": _coord(action, "z", -128, 127),
        }
    if kind == "use_skill":
        return {"type": "use_skill", "skill": _name(action, "skill"),
                "target": _target(action)}
    if kind == "cast":
        return {"type": "cast", "spell": _name(action, "spell"),
                "target": _target(action)}
    if kind == "use_item":
        return {"type": "use_item", "serial": _serial(action, "serial"),
                "target": _target(action)}
    if kind == "equip":
        return {"type": "equip", "serial": _serial(action, "serial")}
    if kind == "war_mode":
        on = action.get("on")
        if not isinstance(on, bool):
            raise InvalidAction("'on' must be true or false")
        return {"type": "war_mode", "on": on}
    if kind == "say":
        text = action.get("text")
        if not isinstance(text, str) or not text.strip():
            raise InvalidAction("'text' must be a non-empty string")
        if len(text) > MAX_SAY_LENGTH or "\n" in text or "\r" in text:
            raise InvalidAction("'text' must be one line of at most {0} characters".format(MAX_SAY_LENGTH))
        return {"type": "say", "text": text.strip()}
    # stop
    reason = action.get("reason", "")
    if not isinstance(reason, str):
        reason = ""
    return {"type": "stop", "reason": reason[:200]}


def describe(action):
    """Short human-readable form for the UI and log."""
    kind = action["type"]
    target = action.get("target")
    suffix = ""
    if target == "self":
        suffix = " on self"
    elif isinstance(target, dict):
        suffix = " on tile ({0}, {1})".format(target["x"], target["y"])
    elif target:
        suffix = " on 0x{0:08X}".format(target)
    if kind == "wait":
        return "wait {0} ms".format(action["ms"])
    if kind == "walk":
        return "walk {0}".format(action["direction"])
    if kind == "move_to":
        return "move to ({0}, {1}, {2})".format(action["x"], action["y"], action["z"])
    if kind == "use_skill":
        return "use skill {0}{1}".format(action["skill"], suffix)
    if kind == "cast":
        return "cast {0}{1}".format(action["spell"], suffix)
    if kind == "use_item":
        return "use item 0x{0:08X}{1}".format(action["serial"], suffix)
    if kind == "equip":
        return "equip 0x{0:08X}".format(action["serial"])
    if kind == "war_mode":
        return "war mode {0}".format("on" if action["on"] else "off")
    if kind == "say":
        return "say \"{0}\"".format(action["text"])
    return "stop ({0})".format(action.get("reason") or "no reason given")
