"""Proves the network guard in conftest.py actually blocks sockets.

If this test ever passes by *reaching the network*, the guard is broken and the
rest of the suite is no longer network-free. The guard must fail loudly on ANY
attempt to open a TCP connection.
"""

import socket

import httpx
import pytest


def test_raw_socket_connect_is_blocked():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(RuntimeError) as ei:
        s.connect(("93.184.216.34", 80))  # never actually dialed
    assert "network" in str(ei.value).lower()
    assert "blocked" in str(ei.value).lower()


def test_create_connection_is_blocked():
    with pytest.raises(RuntimeError) as ei:
        socket.create_connection(("93.184.216.34", 80), timeout=1)
    assert "blocked" in str(ei.value).lower()


def test_httpx_request_is_blocked():
    # Real network code (httpx) must not be able to slip past the guard.
    with pytest.raises(RuntimeError) as ei:
        httpx.get("http://93.184.216.34/", timeout=1)
    assert "blocked" in str(ei.value).lower()
