"""Focused protocol checks for the AX200 monitor helper IPC reader."""

import base64
import json
import unittest
from unittest import mock

import trio

from frlgsim.transport import (
    MonitorHelperError, _MonitorAdvertisementSource, _resolve_keys_path,
)


async def _source_with(message):
    left, right = trio.socket.socketpair()
    source = _MonitorAdvertisementSource(trio.SocketStream(left))
    peer = trio.SocketStream(right)
    await peer.send_all(json.dumps(message).encode() + b"\n")
    return source, peer


class MonitorIpcTests(unittest.TestCase):
    def test_pkexec_default_keys_path_uses_invoking_user(self):
        with mock.patch("frlgsim.transport.pwd.getpwuid") as getpwuid:
            getpwuid.return_value.pw_dir = "/home/tester"
            self.assertEqual(
                _resolve_keys_path("~/.switch/prod.keys", {"PKEXEC_UID": "1000"}, 0),
                "/home/tester/.switch/prod.keys",
            )

    def test_valid_advertisement(self):
        async def run():
            source, peer = await _source_with({"version": 1, "type": "ready"})
            await source.expect_ready()
            action = base64.b64encode(b"ldn-action").decode()
            await peer.send_all(json.dumps({
                "version": 1, "type": "advertisement",
                "source": "001122334455", "frequency": 2437, "action": action,
            }).encode() + b"\n")
            self.assertEqual(
                await source.receive_advertisement(),
                (bytes.fromhex("001122334455"), 2437, b"ldn-action"),
            )
            await source.aclose()
            await peer.aclose()

        trio.run(run)

    def test_invalid_advertisement_fails_closed(self):
        async def run():
            source, peer = await _source_with({"version": 1, "type": "ready"})
            await source.expect_ready()
            await peer.send_all(b'{"version":1,"type":"advertisement","source":"bad"}\n')
            with self.assertRaises(MonitorHelperError):
                await source.receive_advertisement()
            await source.aclose()
            await peer.aclose()

        trio.run(run)

    def test_stats_are_consumed_before_advertisement(self):
        async def run():
            source, peer = await _source_with({"version": 1, "type": "ready"})
            await source.expect_ready()
            await peer.send_all(json.dumps({
                "version": 1, "type": "stats", "phase": "authorized",
                "raw": 9, "radiotap": 8, "action": 7, "vendor": 6,
                "advertisement": 5,
            }).encode() + b"\n")
            action = base64.b64encode(b"ldn-action").decode()
            await peer.send_all(json.dumps({
                "version": 1, "type": "advertisement",
                "source": "001122334455", "frequency": 2437, "action": action,
            }).encode() + b"\n")
            await source.receive_advertisement()
            self.assertEqual(source.stats["vendor"], 6)
            self.assertEqual(source.stats["phase"], "authorized")
            await source.aclose()
            await peer.aclose()

        trio.run(run)

    def test_authorization_marker_is_sent_to_helper(self):
        async def run():
            source, peer = await _source_with({"version": 1, "type": "ready"})
            await source.expect_ready()
            await source.mark_authorized()
            self.assertEqual(
                await peer.receive_some(1024),
                b'{"version":1,"type":"mark","phase":"authorized"}\n',
            )
            await source.aclose()
            await peer.aclose()

        trio.run(run)

    def test_invalid_stats_fail_closed(self):
        async def run():
            source, peer = await _source_with({"version": 1, "type": "ready"})
            await source.expect_ready()
            await peer.send_all(json.dumps({
                "version": 1, "type": "stats", "phase": "authorized",
                "raw": -1, "radiotap": 0, "action": 0, "vendor": 0,
                "advertisement": 0,
            }).encode() + b"\n")
            with self.assertRaises(MonitorHelperError):
                await source.receive_advertisement()
            await source.aclose()
            await peer.aclose()

        trio.run(run)
