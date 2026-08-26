"""Focused protocol checks for the AX200 monitor helper IPC reader."""

import base64
import json
import unittest

import trio

from frlgsim.transport import MonitorHelperError, _MonitorAdvertisementSource


async def _source_with(message):
    left, right = trio.socket.socketpair()
    source = _MonitorAdvertisementSource(trio.SocketStream(left))
    peer = trio.SocketStream(right)
    await peer.send_all(json.dumps(message).encode() + b"\n")
    return source, peer


class MonitorIpcTests(unittest.TestCase):
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
