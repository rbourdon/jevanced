"""Lumberjacking moves for Jev to choose between.

The code does the bookkeeping: which trees are in reach, which have run
out of wood, whether a chop is still under way, how heavy the pack is.
Jev picks the move: chop, walk to the next tree, equip the axe or cut logs
into boards, alongside the safety moves every task has.

Stopping is decided in code when it's a matter of counting or of having
nothing left to do (``finished``): enough wood, no axe, a full pack, no
trees with wood. Jev is only offered "stop" when the player wrote
instructions, since those are words the code can't check.

A chop is one use of the axe on a tree; the shard answers with a message
("You put some logs into your backpack", "There's not enough wood here to
harvest", ...). Until that message arrives (or CHOP_TIMEOUT_S passes) no
new chop is offered, so jevanced doesn't spam the axe or ask Jev about it.
"""

from jevanced.jev.option import Option
from jevanced.lumber import AXE_IDS, BOARD_IDS, LOG_IDS, REACH, bank
from jevanced.state import is_game_message

CHOP_TIMEOUT_S = 8.0
EMPTY_BANK_S = 20 * 60.0  # the shard regrows wood after 20 to 30 minutes
BAD_TREE_S = 5 * 60.0
MAX_WALKS_TO_TREE = 6
NEARLY_FULL = 0.85

# Substrings of the shard's replies to a chop, and what they mean.
GOT_WOOD = ("into your backpack", "You put some")
NO_WOOD = ("not enough wood",)
FAILED = ("fail to produce",)
UNREACHABLE = ("too far away", "can't use an axe on that", "cannot be seen")
BUSY = ("must wait",)
PACK_FULL = ("can't place any wood",)
NEEDS_EQUIP = ("must be equipped",)
AXE_BROKE = ("broke your axe",)


def _key(tree):
    return (tree["position"][0], tree["position"][1])


def _sign(n):
    if n > 0:
        return 1
    return -1 if n < 0 else 0


def _tiles(n):
    return "1 tile" if n == 1 else "{0} tiles".format(n)


class Memory(object):
    """What jevanced remembers between turns while lumberjacking."""

    def __init__(self):
        self.chop_started = None  # when the last chop was sent, until it answers
        self.chop_tree = None
        self.last_result = "none yet"
        self.empty_banks = {}  # bank -> time it may have wood again
        self.bad_trees = {}  # (x, y) -> time to try it again
        self.walks = {}  # (x, y) -> times we walked towards it
        self.logs_cut = 0

    # ---- after each state read ----------------------------------------

    def observe(self, state):
        now = state.get("timestamp", 0.0)
        for line in state.get("journal", []):
            if not is_game_message(line):
                continue
            self._read_message(line.get("text", ""), now, state)
        if self.chop_started is not None and now - self.chop_started >= CHOP_TIMEOUT_S:
            self.chop_started = None

    def _read_message(self, text, now, state):
        def has(parts):
            return any(p in text for p in parts)

        tree = self.chop_tree
        if has(PACK_FULL):
            # Checked first: its text also ends "into your backpack!".
            self.last_result = "backpack can't hold more wood"
            self.chop_started = None
            return
        if has(BUSY):
            self.chop_started = now
            return
        if has(GOT_WOOD):
            self.last_result = "got logs"
            self.logs_cut += 1
            if tree:
                self.walks.pop(_key(tree), None)
        elif has(FAILED):
            self.last_result = "swung but got no wood; this tree still has wood"
        elif has(NO_WOOD):
            self.last_result = "this tree has no wood left"
            if tree:
                self.empty_banks[self._bank(state, tree)] = now + EMPTY_BANK_S
        elif has(UNREACHABLE):
            self.last_result = "couldn't reach that tree"
            if tree:
                self.bad_trees[_key(tree)] = now + BAD_TREE_S
        elif has(NEEDS_EQUIP):
            self.last_result = "the axe has to be in your hands"
        elif has(AXE_BROKE):
            self.last_result = "your axe broke"
        else:
            return
        self.chop_started = None

    @staticmethod
    def _bank(state, tree):
        map_id = state.get("player", {}).get("map", 0)
        return bank(map_id, tree["position"][0], tree["position"][1])

    # ---- after Jev picks ----------------------------------------------

    def chopped(self, tree, now):
        self.chop_started = now
        self.chop_tree = tree

    def walked_to(self, tree):
        key = _key(tree)
        self.walks[key] = self.walks.get(key, 0) + 1

    # ---- queries -------------------------------------------------------

    def chopping(self):
        return self.chop_started is not None

    def usable(self, state, tree):
        now = state.get("timestamp", 0.0)
        if self.empty_banks.get(self._bank(state, tree), 0) > now:
            return False
        if self.bad_trees.get(_key(tree), 0) > now:
            return False
        return self.walks.get(_key(tree), 0) < MAX_WALKS_TO_TREE


def _find(items, ids):
    for item in items:
        if item.get("item_id") in ids:
            return item
    return None


def _count(items, ids):
    return sum(i.get("amount", 0) for i in items if i.get("item_id") in ids)


def _load(player):
    weight, most = player.get("weight", 0), player.get("max_weight", 0)
    if most <= 0:
        return "unknown", 0.0
    fraction = float(weight) / most
    if fraction >= 1.0:
        words = "overloaded"
    elif fraction >= NEARLY_FULL:
        words = "nearly full"
    elif fraction >= 0.5:
        words = "half full"
    else:
        words = "light"
    return "{0} of {1} stones ({2})".format(weight, most, words), fraction


class Situation(object):
    """The lumberjacking facts for one turn, worked out once."""

    def __init__(self, state, memory):
        player = state.get("player", {})
        self.axe_in_hand = _find(state.get("equipped", []), AXE_IDS)
        self.axe_in_pack = _find(state.get("backpack", []), AXE_IDS)
        self.logs = _find(state.get("backpack", []), LOG_IDS)
        self.log_count = _count(state.get("backpack", []), LOG_IDS)
        self.board_count = _count(state.get("backpack", []), BOARD_IDS)
        self.load_words, self.load = _load(player)
        trees = [t for t in state.get("trees", []) if memory.usable(state, t)]
        in_reach = [t for t in trees if t.get("distance", 99) <= REACH]
        self.tree_in_reach = in_reach[0] if in_reach else None
        farther = [t for t in trees if t.get("distance", 99) > REACH]
        self.next_tree = farther[0] if farther else None
        self.position = player.get("position", [0, 0, 0])
        self.chopping = memory.chopping()
        self.last_result = memory.last_result
        task = state.get("task") or {}
        self.wood = self.log_count + self.board_count
        self.wood_goal = task.get("wood_goal") or 0
        self.has_instructions = bool(task.get("instructions"))


def finished(state, memory):
    """Why lumberjacking is over, or None while there's work to do."""
    s = Situation(state, memory)
    if s.chopping:
        return None
    if s.wood_goal and s.wood >= s.wood_goal:
        return "Done: carrying {0} wood, and you asked for {1}.".format(s.wood, s.wood_goal)
    if s.axe_in_hand is None and s.axe_in_pack is None:
        return "No axe to chop with."
    if s.load >= 1.0 and (s.logs is None or s.axe_in_hand is None):
        return "Your backpack is too heavy to carry more wood."
    if s.tree_in_reach is None and s.next_tree is None:
        return "No trees with wood left nearby. Move somewhere new and start again."
    return None


def options(state, memory):
    """The lumberjacking moves that make sense now."""
    s = Situation(state, memory)
    found = []
    if s.axe_in_hand is None and s.axe_in_pack is not None:
        found.append(Option(
            "equip_axe",
            "Take the axe from your backpack into your hands. Right when you "
            "have no axe in hand, since you can only chop with one.",
            {"type": "equip", "serial": s.axe_in_pack["serial"]}))

    if s.axe_in_hand is not None and not s.chopping:
        if s.tree_in_reach is not None and s.load < 1.0:
            tree = s.tree_in_reach
            found.append(Option(
                "chop",
                "Chop the tree {0} away with your axe. Right when you're "
                "lumberjacking and can carry more.".format(_tiles(tree["distance"])),
                {"type": "use_item", "serial": s.axe_in_hand["serial"],
                 "target": {"x": tree["position"][0], "y": tree["position"][1],
                            "z": tree["position"][2], "tile": tree["tile_id"]}}))
        if s.logs is not None and s.load >= NEARLY_FULL:
            found.append(Option(
                "make_boards",
                "Cut the logs you carry into boards, which weigh half as much. "
                "Right when you are nearly too heavy to carry more wood.",
                {"type": "use_item", "serial": s.axe_in_hand["serial"],
                 "target": s.logs["serial"]}))

    if s.tree_in_reach is None and s.next_tree is not None and not s.chopping:
        tree = s.next_tree
        tx, ty, tz = tree["position"]
        # The tile beside the tree on your side: trees block their own tile.
        x = tx - _sign(tx - s.position[0])
        y = ty - _sign(ty - s.position[1])
        found.append(Option(
            "go_to_tree",
            "Walk to the next tree, {0} away. Right when no tree in reach has "
            "wood left.".format(_tiles(tree["distance"])),
            {"type": "move_to", "x": x, "y": y, "z": tz}))

    if s.has_instructions and not s.chopping:
        found.append(Option(
            "stop",
            "Stop lumberjacking and end the session. Right only when the "
            "player's instructions say to stop now.",
            {"type": "stop", "reason": "Jev followed your instructions and stopped"}))
    return found


def describe(state, memory):
    """The lumberjacking part of what Jev sees."""
    s = Situation(state, memory)
    if s.axe_in_hand is not None:
        axe = "in your hands"
    elif s.axe_in_pack is not None:
        axe = "in your backpack, not in your hands"
    else:
        axe = "none"
    seen = {
        "axe": axe,
        "logs carried": s.log_count,
        "boards carried": s.board_count,
        "wood carried in all (logs and boards)": s.log_count + s.board_count,
        "load": s.load_words,
        "chopping now": "yes, waiting for the result" if s.chopping else "no",
        "last chop": s.last_result,
        "tree in reach with wood": "yes" if s.tree_in_reach else "no",
        "next tree": _tiles(s.next_tree["distance"]) + " away" if s.next_tree else "none found nearby",
    }
    if s.wood_goal:
        seen["wood wanted"] = s.wood_goal
    return seen
