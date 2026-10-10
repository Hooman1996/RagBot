"""Opt-in offline verification: fail unintended network/database access."""
import socket
import psycopg2

_originals = []


def blocked(*args, **kwargs):
    raise AssertionError("Offline verification blocked an unmocked external operation")


def pytest_configure(config):
    for owner, name in ((socket.socket, "connect"), (socket.socket, "connect_ex"),
                        (socket, "getaddrinfo"), (psycopg2, "connect")):
        _originals.append((owner, name, getattr(owner, name)))
        setattr(owner, name, blocked)


def pytest_unconfigure(config):
    while _originals:
        owner, name, original = _originals.pop()
        setattr(owner, name, original)
