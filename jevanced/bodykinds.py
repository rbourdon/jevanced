"""What kind of creature a body id is: monster, animal, sea monster or human.

On many shards monsters and animals both show a grey name, and monsters
often have personal names ("Hibub" is an orc), so neither colour nor name
tells Jev what it's looking at. The UO client ships mobtypes.txt, which
files every body id under a type; the adapter finds that file and this
module reads it.
"""

KINDS = {
    "MONSTER": "monster",
    "ANIMAL": "animal",
    "SEA_MONSTER": "sea monster",
    "HUMAN": "human",
}


def parse_mobtypes(text):
    """Map body id to kind from mobtypes.txt ("ID TYPE FLAGS" per line)."""
    kinds = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[0].startswith("#"):
            continue
        try:
            body = int(parts[0])
        except ValueError:
            continue
        kind = KINDS.get(parts[1].upper())
        if kind:
            kinds[body] = kind
    return kinds
