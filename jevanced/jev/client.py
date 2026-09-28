"""The interface between jevanced and Jev.

This fixes the shape jevanced needs from a decision maker: check a key,
and turn a game state into one action. ``typesafe.TypesafeJevClient`` is
the real Jev; ``stub.StubJevClient`` is an offline stand-in.
"""


class JevError(Exception):
    """Anything that went wrong talking to Jev."""


class JevAuthError(JevError):
    """Jev rejected the API key. The loop stops; retrying won't help."""


class JevUnavailableError(JevError):
    """Jev couldn't be reached or timed out. Worth retrying."""


class JevResponseError(JevError):
    """Jev answered with something jevanced can't use."""


class KeyCheck(object):
    """Result of checking a key.

    ``verified`` is True only when Jev itself confirmed the key. A client
    that can't reach Jev (like the offline stub) reports False with a
    message saying why.
    """

    def __init__(self, verified, message):
        self.verified = verified
        self.message = message


class JevClient(object):
    """Base class every Jev client implements."""

    #: Shown in the UI so the user knows what's making decisions.
    display_name = "Jev"

    #: A short line on the last decision (why it waited, what it chose and
    #: how sure it was). The loop logs it when it changes.
    last_note = ""

    def check_key(self):
        """Return a KeyCheck, or raise JevAuthError if the key is rejected."""
        raise NotImplementedError

    def decide(self, state):
        """Return one action dict (see jevanced.actions) for ``state``.

        ``state`` is the dict from GameState.to_dict(). Raise JevAuthError,
        JevUnavailableError or JevResponseError on failure.
        """
        raise NotImplementedError

    def close(self):
        pass
