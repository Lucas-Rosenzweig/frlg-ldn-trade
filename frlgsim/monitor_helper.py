"""Private AX200 monitor helper.

This module is launched only by :mod:`frlgsim.transport`.  It binds an existing
monitor VIF in a separate process and forwards only decodable LDN advertisements
over a private Unix socket; it never logs radio identifiers or payloads.
"""

import argparse
import base64
import json
import logging
import socket

import trio

import ldn
from ldn import wlan


MAX_MESSAGE = 65536
_ADVERTISEMENT_HEADER = b"\x7f\x00\x22\xaa\x04\x00\x01\x01"


class MonitorReader:
    """Minimal raw reader for an existing monitor VIF."""

    def __init__(self, ifname):
        self._ifname = ifname
        self._socket = trio.socket.socket(
            socket.AF_PACKET, socket.SOCK_RAW, socket.htons(wlan.ETH_P_ALL)
        )

    async def activate(self):
        await self._socket.bind((self._ifname, 0))

    async def recv(self):
        while True:
            data = await self._socket.recv(4096)
            radiotap = wlan.RadiotapFrame()
            try:
                radiotap.decode(data)
                return radiotap
            except Exception:
                continue

    def close(self):
        self._socket.close()


async def _send(stream, message):
    data = json.dumps(message, separators=(",", ":")).encode() + b"\n"
    if len(data) > MAX_MESSAGE:
        raise RuntimeError("monitor IPC message exceeds limit")
    await stream.send_all(data)


async def serve(socket_path, ifname, keys_path):
    keys = ldn.load_keys(keys_path)
    derivations = {
        protocol: ldn.KeyDerivation(keys, protocol) for protocol in (1, 3)
    }
    sock = trio.socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    await sock.connect(socket_path)
    stream = trio.SocketStream(sock)
    reader = MonitorReader(ifname)
    try:
        await reader.activate()
        await _send(stream, {"version": 1, "type": "ready"})
        while True:
            radiotap = await reader.recv()
            if radiotap.frequency is None:
                continue
            action = wlan.ActionFrame()
            try:
                action.decode(radiotap.data)
            except Exception:
                continue
            if not action.action.startswith(_ADVERTISEMENT_HEADER):
                continue
            for protocol, derivation in derivations.items():
                frame = ldn.AdvertisementFrame(derivation, protocol)
                try:
                    frame.decode(action.action)
                except Exception:
                    continue
                await _send(stream, {
                    "version": 1,
                    "type": "advertisement",
                    "source": bytes(action.source).hex(),
                    "frequency": radiotap.frequency,
                    "action": base64.b64encode(action.action).decode(),
                })
                break
    finally:
        reader.close()
        await stream.aclose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--iface", required=True)
    parser.add_argument("--keys", required=True)
    args = parser.parse_args()
    logging.getLogger("ldn").setLevel(logging.ERROR)
    trio.run(serve, args.socket, args.iface, args.keys)


if __name__ == "__main__":
    main()
