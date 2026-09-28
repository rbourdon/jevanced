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
    if backend == "jev":
        from jevanced.jev.typesafe import TypesafeJevClient
        return TypesafeJevClient(api_key)
    if backend == "stub":
        from jevanced.jev.stub import StubJevClient
        return StubJevClient(api_key)
    raise ValueError("Unknown Jev backend: {0!r}".format(backend))
