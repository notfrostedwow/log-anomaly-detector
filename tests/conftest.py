"""All tests forbid network connections, including accidental SDK requests."""

import socket
from pathlib import Path

import pytest


def pytest_sessionstart(session: pytest.Session) -> None:
    """Create an explicit basetemp's parents before pytest builds tmp_path fixtures."""
    basetemp = session.config.getoption("basetemp")
    if basetemp is not None:
        Path(basetemp).parent.mkdir(parents=True, exist_ok=True)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network is forbidden in this test suite")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
