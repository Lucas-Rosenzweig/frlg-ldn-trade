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

    def __init__(self, ifname, stats):
        self._ifname = ifname
        self._stats = stats
        self._socket = trio.socket.socket(
            socket.AF_PACKET, socket.SOCK_RAW, socket.htons(wlan.ETH_P_ALL)
        )

    async def activate(self):
        await self._socket.bind((self._ifname, 0))

    async def recv(self):
        while True:
            data = await self._socket.recv(4096)
            self._stats["raw"] += 1
            radiotap = wlan.RadiotapFrame()
            try:
                radiotap.decode(data)
                self._stats["radiotap"] += 1
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


async def _receive_marks(stream, state):
    buffer = bytearray()
    while True:
        data = await stream.receive_some(MAX_MESSAGE)
        if not data:
            return
        buffer.extend(data)
        if len(buffer) > MAX_MESSAGE:
            raise RuntimeError("monitor IPC control message exceeds limit")
        while b"\n" in buffer:
            line, _, remainder = buffer.partition(b"\n")
            buffer[:] = remainder
            message = json.loads(line)
            if message != {"version": 1, "type": "mark", "phase": "authorized"}:
                raise RuntimeError("monitor helper received an invalid control message")
            state["phase"] = "authorized"


async def _send_stats(stream, state, stats):
    await _send(stream, {
        "version": 1, "type": "stats", "phase": state["phase"], **stats,
    })


async def serve(socket_path, ifname, keys_path):
    keys = ldn.load_keys(keys_path)
    derivations = {
        protocol: ldn.KeyDerivation(keys, protocol) for protocol in (1, 3)
    }
    sock = trio.socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    await sock.connect(socket_path)
    stream = trio.SocketStream(sock)
    state = {"phase": "pre-join"}
    stats = {name: 0 for name in ("raw", "radiotap", "action", "vendor", "advertisement")}
    reader = MonitorReader(ifname, stats)
    try:
        await reader.activate()
        await _send(stream, {"version": 1, "type": "ready"})
        async with trio.open_nursery() as nursery:
            nursery.start_soon(_receive_marks, stream, state)
            last_stats = trio.current_time()
            while True:
                radiotap = None
                with trio.move_on_after(.5):
                    radiotap = await reader.recv()
                if radiotap is not None:
                    if radiotap.frequency is not None:
                        action = wlan.ActionFrame()
                        try:
                            action.decode(radiotap.data)
                            stats["action"] += 1
                        except Exception:
                            action = None
                        if action is not None and action.action.startswith(_ADVERTISEMENT_HEADER):
                            stats["vendor"] += 1
                            for protocol, derivation in derivations.items():
                                frame = ldn.AdvertisementFrame(derivation, protocol)
                                try:
                                    frame.decode(action.action)
                                except Exception:
                                    continue
                                stats["advertisement"] += 1
                                await _send(stream, {
                                    "version": 1, "type": "advertisement",
                                    "source": bytes(action.source).hex(),
                                    "frequency": radiotap.frequency,
                                    "action": base64.b64encode(action.action).decode(),
                                })
                                break
                now = trio.current_time()
                if now - last_stats >= .5:
                    await _send_stats(stream, state, stats)
                    last_stats = now
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
