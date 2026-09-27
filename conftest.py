"""Network guard for the test suite.

Tests in this spike are network-free by construction: all network code is
exercised through a fake httpx transport fed recorded responses. To make that
guarantee enforceable rather than aspirational, this conftest replaces the
socket connect primitives with a guard that raises loudly on ANY attempt to
open a real TCP connection.

Live discovery (spike items 5-7) is run through standalone scripts invoked
directly, NOT under pytest, so this guard never interferes with real probing.
"""

import socket

_GUARD_MESSAGE = (
    "Network access is blocked in tests. All network code must be exercised "
    "through the fake transport with recorded responses. If you see this, a "
    "test tried to open a real socket."
)


class NetworkBlockedError(RuntimeError):
    """Raised when test code attempts to open a real network connection."""


def _blocked(*_args, **_kwargs):
    raise NetworkBlockedError(_GUARD_MESSAGE)


# Install the guard at import time (collection), so even import-time connects
# are caught, not just those inside a fixture's scope.
socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked
socket.create_connection = _blocked
