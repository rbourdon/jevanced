from jevanced.jev.client import (  # noqa: F401
    JevAuthError,
    JevClient,
    JevError,
    JevResponseError,
    JevUnavailableError,
    KeyCheck,
)


def make_client(backend, api_key):
    """Build the Jev client named in settings."""
    if backend == "stub":
        from jevanced.jev.stub import StubJevClient
        return StubJevClient(api_key)
    raise ValueError("Unknown Jev backend: {0!r}".format(backend))
