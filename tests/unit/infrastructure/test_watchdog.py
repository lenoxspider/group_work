"""Tests for the systemd watchdog notify helper.

The property that matters most is that notify() can never raise: a watchdog that
takes the process down with it is worse than no watchdog at all.
"""

import os
import socket
import tempfile
import unittest

from src.infrastructure.watchdog import HEARTBEAT_SECONDS, is_under_systemd, notify

# The unit file sets WatchdogSec=60.
WATCHDOG_SEC = 60


# Only the two tests that bind a real socket need AF_UNIX. Skipping the whole
# class on Windows hid a genuine bug: notify() caught OSError, but a missing
# socket.AF_UNIX raises AttributeError, which would have escaped.
HAS_AF_UNIX = hasattr(socket, "AF_UNIX")


class TestSdNotify(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("NOTIFY_SOCKET")
        os.environ.pop("NOTIFY_SOCKET", None)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("NOTIFY_SOCKET", None)
        else:
            os.environ["NOTIFY_SOCKET"] = self._saved

    def _server(self, directory):
        path = os.path.join(directory, "notify.sock")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        server.bind(path)
        server.settimeout(3)
        return path, server

    def test_without_a_socket_it_is_a_quiet_noop(self):
        """A laptop or a test run has no NOTIFY_SOCKET and must not care."""
        self.assertFalse(is_under_systemd())
        self.assertFalse(notify("READY=1"))

    def test_the_datagram_reaches_the_socket(self):
        if not HAS_AF_UNIX:
            self.skipTest("AF_UNIX unavailable on this platform")
        with tempfile.TemporaryDirectory() as d:
            path, server = self._server(d)
            try:
                os.environ["NOTIFY_SOCKET"] = path
                self.assertTrue(is_under_systemd())
                self.assertTrue(notify("WATCHDOG=1"))
                data, _ = server.recvfrom(1024)
                self.assertEqual(data, b"WATCHDOG=1")
            finally:
                server.close()

    def test_ready_and_watchdog_are_both_sent_verbatim(self):
        if not HAS_AF_UNIX:
            self.skipTest("AF_UNIX unavailable on this platform")
        with tempfile.TemporaryDirectory() as d:
            path, server = self._server(d)
            try:
                os.environ["NOTIFY_SOCKET"] = path
                for state in ("READY=1", "WATCHDOG=1"):
                    self.assertTrue(notify(state))
                    data, _ = server.recvfrom(1024)
                    self.assertEqual(data, state.encode())
            finally:
                server.close()

    def test_a_broken_socket_does_not_raise(self):
        os.environ["NOTIFY_SOCKET"] = "/nonexistent/directory/notify.sock"
        self.assertFalse(notify("READY=1"))

    @unittest.skipIf(HAS_AF_UNIX, "guards the no-AF_UNIX path only")
    def test_a_platform_without_af_unix_returns_false_not_attributeerror(self):
        """Regression for the bug the blanket skip concealed."""
        os.environ["NOTIFY_SOCKET"] = "/run/systemd/notify"
        self.assertFalse(is_under_systemd())
        self.assertFalse(notify("READY=1"))

    def test_heartbeat_leaves_room_for_missed_beats(self):
        """Ordinary slowness must not look like a hang and trigger a restart."""
        self.assertLessEqual(HEARTBEAT_SECONDS * 3, WATCHDOG_SEC)


if __name__ == "__main__":
    unittest.main()
