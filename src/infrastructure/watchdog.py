"""systemd watchdog support, without taking a dependency on sdnotify.

The failure this exists for: every bug found during hardening was *silent*. Dead
reminders, a hung command, a swallowed money error. The one class nothing catches
is a hung event loop - the process stays alive and connected-looking, so
systemd's Restart=always never fires because from its point of view nothing is
wrong.

Under Type=notify with WatchdogSec set, systemd kills and restarts the service
if it stops hearing from it. The heartbeat is sent from the event loop itself
(see GroupAccountabilityBot), which is the whole point: if the loop blocks, the
pings stop. A heartbeat from a separate thread would keep beating over a dead
loop and prove nothing.

The protocol is one datagram to the socket in $NOTIFY_SOCKET, so it needs no
third-party package. Outside systemd - a laptop, a test run - notify() is a
quiet no-op and the heartbeat task is never started.
"""

import logging
import os
import socket

logger = logging.getLogger("infrastructure.watchdog")

# How often to ping. Must sit comfortably inside the unit's WatchdogSec so that
# ordinary slowness (a big query, an image render) cannot cause a restart.
HEARTBEAT_SECONDS = 20


def notify(state: str) -> bool:
    """Send one sd_notify datagram. True if it was delivered.

    Never raises: a watchdog that can take the process down with it would be
    worse than no watchdog at all.
    """
    path = os.environ.get("NOTIFY_SOCKET")
    if not path:
        return False
    if not hasattr(socket, "AF_UNIX"):
        # Windows has no AF_UNIX and no systemd. Without this guard the
        # AttributeError below would escape, and it is not an OSError.
        return False
    if path.startswith("@"):  # abstract namespace socket
        path = "\0" + path[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(path)
            sock.sendall(state.encode("utf-8"))
        return True
    except Exception as exc:
        logger.warning("Could not notify systemd (%s): %s", state.split("=")[0], exc)
        return False


def is_under_systemd() -> bool:
    """True when running under systemd with notifications actually available."""
    return bool(os.environ.get("NOTIFY_SOCKET")) and hasattr(socket, "AF_UNIX")
