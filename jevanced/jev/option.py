class Option(object):
    """One move Jev can choose: a key, plain-words criteria, and the action."""

    def __init__(self, key, description, action):
        self.key = key
        self.description = description
        self.action = action
