"""The jobs a user can give jevanced, picked in the window.

Each task has a fixed goal and its own set of moves (see
``jevanced.jev.choices``). The user's own instructions, typed in the
window, are passed to Jev alongside the goal.
"""

STAY_SAFE = "stay_safe"
LUMBERJACK = "lumberjack"

# (name, label shown in the window), in the order the window lists them.
TASKS = (
    (STAY_SAFE, "Stay safe: heal and keep away from monsters"),
    (LUMBERJACK, "Lumberjack: chop the trees around you"),
)
NAMES = tuple(name for name, _ in TASKS)
MAX_INSTRUCTIONS = 200
MAX_WOOD_GOAL = 10000


def label(name):
    return dict(TASKS).get(name, name)


def clean_instructions(text):
    """One line of at most MAX_INSTRUCTIONS characters."""
    if not isinstance(text, str):
        return ""
    return " ".join(text.split())[:MAX_INSTRUCTIONS]
