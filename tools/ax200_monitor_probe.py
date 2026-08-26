#!/usr/bin/env python3
"""Count decodable LDN advertisements on an existing monitor interface.

This is a diagnostic for the AX200 station+monitor experiment.  It does not
create, retune, or delete an interface: create ``mon0`` on the same PHY as the
LDN station first, then run this probe while the join is in progress.  Its only
output is an aggregate count, so captures and advertisement identifiers remain
local.
"""

import argparse
import logging
import socket
import time
from collections import Counter

import trio

import ldn
from ldn import wlan


class ExistingMonitor:
    """Minimal Scanner-compatible reader for an already-created monitor VIF."""

    def __init__(self, ifname):
        self._socket = trio.socket.socket(
            socket.AF_PACKET, socket.SOCK_RAW, socket.htons(wlan.ETH_P_ALL)
        )
        self._ifname = ifname

    def set_filter(self, _filter):
        # Scanner calls this for its normal broadcast-BSSID filter.  It parses
        # and validates each advertisement itself, so kernel-level filtering is
        # unnecessary for this receive-only diagnostic.
        pass

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


async def probe(ifname, keys_path, duration):
    keys = ldn.load_keys(keys_path)
    protocols = {
        protocol: ldn.KeyDerivation(keys, protocol)
        for protocol in (1, 3)
    }
    monitor = ExistingMonitor(ifname)
    await monitor.activate()
    scanner = ldn.Scanner(protocols, monitor)
    received_at = []
    started_at = time.monotonic()
    try:
        with trio.move_on_after(duration):
            while True:
                await scanner.receive()
                received_at.append(time.monotonic() - started_at)
    finally:
        monitor.close()
    return received_at


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iface", default="mon0", help="existing monitor VIF (default: mon0)")
    parser.add_argument("--keys", required=True, help="absolute path to prod.keys")
    parser.add_argument("--duration", type=float, default=12.0, metavar="SECONDS",
                        help="receive window (default: 12)")
    parser.add_argument("--per-second", action="store_true",
                        help="report only aggregate counts by elapsed second")
    args = parser.parse_args()
    if args.duration <= 0:
        parser.error("--duration must be positive")

    logging.getLogger("ldn").setLevel(logging.ERROR)
    received_at = trio.run(probe, args.iface, args.keys, args.duration)
    print(f"decodable LDN advertisements on {args.iface}: {len(received_at)}")
    if args.per_second:
        counts = Counter(int(elapsed) for elapsed in received_at)
        print("per-second counts: " + " ".join(
            f"{second}:{counts[second]}" for second in range(int(args.duration))
        ))


if __name__ == "__main__":
    main()
