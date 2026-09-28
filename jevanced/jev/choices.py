"""Turns a game state into the options Jev chooses between.

Jev doesn't invent actions. It answers typed questions, so jevanced's own
code lists the moves that make sense right now (bandage when hurt, step
away from a monster, or wait), describes each in
plain words, and asks Jev which one to take. Anything that is arithmetic,
like distances, cooldowns and directions, stays here in code.

Typesafe's notes on Jev (docs.typesafe.ai) shape the details: the state
holds only what the decision needs, health is described in words rather
than raw numbers, and other players' chat is left out because text in the
state can steer the answer.
"""

from jevanced import tasks
from jevanced.actions import DIRECTIONS
from jevanced.jev import lumberjack
from jevanced.jev.option import Option  # noqa: F401 (re-exported)
from jevanced.state import is_game_message

BANDAGE_ITEM_ID = 0x0E21
BANDAGE_COOLDOWN_S = 10.0
# What UO's name colours mean, in words Jev reads well.
ATTITUDE = {
    "innocent": "innocent (blue)",
    "ally": "friendly (green)",
    "attackable": "neutral (grey)",
    "criminal": "criminal (grey)",
    "enemy": "enemy (orange)",
    "murderer": "hostile (red)",
    "invulnerable": "invulnerable (yellow)",
}
HOSTILE_COLOURS = ("criminal", "enemy", "murderer")
THREAT_KINDS = ("monster", "sea monster")
KIND_PHRASE = {"monster": "a monster", "animal": "an animal",
               "sea monster": "a sea monster", "human": "a person"}
MAX_CREATURES = 10
STEP_AWAY_WITHIN = 6  # tiles
MAX_MESSAGES = 5

# jevanced never starts a fight: there is no attack option.
GOAL = ("Stay alive and out of fights. Keep away from monsters and hostile "
        "creatures that come close. Heal yourself when you are hurt.")
GOALS = {
    tasks.STAY_SAFE: GOAL,
    tasks.LUMBERJACK: (
        "Chop wood with your axe: keep chopping the tree in reach until it has "
        "no wood left, then walk to the next tree. Follow the player's "
        "instructions. Stay out of fights: step away from monsters that "
        "come close, and heal yourself when you are hurt."),
}
WAIT_WHEN = {
    tasks.STAY_SAFE: ("Do nothing this turn. Right when no monster is within "
                      "a few tiles and you don't need healing."),
    tasks.LUMBERJACK: ("Do nothing this turn. Right only while a chop is "
                       "still under way, or when no other move fits."),
}

INSTRUCTIONS = ("You control the character described in `you`, following `goal`. "
                "Which one action should the character take right now?")

WAIT = {"type": "wait", "ms": 1000}


def health_words(hits, hits_max):
    if hits_max <= 0:
        return "unknown health"
    fraction = float(hits) / hits_max
    percent = int(round(fraction * 100))
    if fraction >= 0.95:
        words = "full health"
    elif fraction >= 0.7:
        words = "lightly hurt"
    elif fraction >= 0.4:
        words = "badly hurt"
    else:
        words = "near death"
    return "{0}% ({1})".format(percent, words)


def _tiles(n):
    return "1 tile" if n == 1 else "{0} tiles".format(n)


def _attitude(mob):
    return ATTITUDE.get(mob.get("notoriety"), "unknown")


def _is_threat(mob):
    return mob.get("kind") in THREAT_KINDS or mob.get("notoriety") in HOSTILE_COLOURS


def _who(mob):
    """ "Hibub, a monster, neutral (grey)" """
    parts = [mob.get("name") or "a creature"]
    if mob.get("kind") in KIND_PHRASE:
        parts.append(KIND_PHRASE[mob["kind"]])
    parts.append(_attitude(mob))
    return ", ".join(parts)


def _threats(state):
    """Living monsters and hostile creatures, nearest first (the state is sorted)."""
    return [mob for mob in state.get("mobiles", [])
            if _is_threat(mob) and mob.get("hits", 0) > 0]


def _bandages(state):
    for item in state.get("backpack", []):
        if item.get("item_id") == BANDAGE_ITEM_ID and item.get("amount", 0) > 0:
            return item
    return None


def _sign(n):
    if n > 0:
        return 1
    return -1 if n < 0 else 0


def direction_away(from_pos, own_pos):
    """The UO direction that steps from ``own_pos`` directly away from ``from_pos``."""
    dx = _sign(own_pos[0] - from_pos[0])
    dy = _sign(own_pos[1] - from_pos[1])
    # DIRECTIONS runs clockwise from North; UO's y axis grows southward.
    table = {(0, -1): 0, (1, -1): 1, (1, 0): 2, (1, 1): 3,
             (0, 1): 4, (-1, 1): 5, (-1, 0): 6, (-1, -1): 7}
    return DIRECTIONS[table.get((dx, dy), 0)]


def task_of(state):
    task = state.get("task") or {}
    name = task.get("name")
    return name if name in tasks.NAMES else tasks.STAY_SAFE


def build_options(state, last_bandage_at=None, lumber=None):
    """The moves worth considering now. "wait" is always first."""
    player = state.get("player", {})
    now = state.get("timestamp", 0.0)
    task = task_of(state)
    options = [Option("wait", WAIT_WHEN[task], WAIT)]

    hits, hits_max = player.get("hits", 0), player.get("hits_max", 0)
    bandages = _bandages(state)
    cooled = last_bandage_at is None or now - last_bandage_at >= BANDAGE_COOLDOWN_S
    if bandages and cooled and 0 < hits < hits_max:
        options.append(Option(
            "bandage_self",
            "Bandage yourself to heal. Right when you are hurt and nothing "
            "dangerous is right next to you.",
            {"type": "use_item", "serial": bandages["serial"], "target": "self"}))

    threats = _threats(state)
    if threats and threats[0].get("distance", 99) <= STEP_AWAY_WITHIN:
        nearest = threats[0]
        options.append(Option(
            "step_away",
            "Step away from {0}, {1} away. Right when it is close enough to "
            "attack you.".format(_who(nearest), _tiles(nearest.get("distance", 0))),
            {"type": "walk",
             "direction": direction_away(nearest["position"], player.get("position", [0, 0, 0]))}))

    if task == tasks.LUMBERJACK:
        options.extend(lumberjack.options(state, lumber or lumberjack.Memory()))
    return options


def finished(state, lumber=None):
    """Why the task is over (decided in code), or None."""
    if task_of(state) == tasks.LUMBERJACK:
        return lumberjack.finished(state, lumber or lumberjack.Memory())
    return None


def describe_state(state, options, lumber=None):
    """What Jev sees: the goal, the character, and what's around it."""
    task = task_of(state)
    instructions = (state.get("task") or {}).get("instructions") or ""
    player = state.get("player", {})
    bandages = _bandages(state)
    creatures = []
    for mob in state.get("mobiles", [])[:MAX_CREATURES]:
        creatures.append({
            "name": mob.get("name") or "a creature",
            "kind": mob.get("kind") or "unknown",
            "attitude": _attitude(mob),
            "distance": _tiles(mob.get("distance", 0)),
            "health": health_words(mob.get("hits", 0), mob.get("hits_max", 0)),
        })
    # Only the game's own messages; players' chat could steer Jev.
    messages = [line["text"] for line in state.get("journal", [])
                if is_game_message(line) and line.get("text")]
    seen = {
        "goal": GOALS[task],
        "you": {
            "health": health_words(player.get("hits", 0), player.get("hits_max", 0)),
            "poisoned": "yes" if player.get("poisoned") else "no",
            "war mode": "on" if player.get("war_mode") else "off",
            "bandages": bandages.get("amount", 0) if bandages else 0,
            "can bandage now": "yes" if any(o.key == "bandage_self" for o in options) else "no",
        },
        "creatures nearby": creatures,
        "recent game messages": messages[-MAX_MESSAGES:],
    }
    if instructions:
        seen["player's instructions"] = instructions
    if task == tasks.LUMBERJACK:
        seen["lumberjacking"] = lumberjack.describe(state, lumber or lumberjack.Memory())
    return seen


def question(options):
    return {
        "type": "choice",
        "instructions": INSTRUCTIONS,
        "criteria": dict((o.key, o.description) for o in options),
    }
