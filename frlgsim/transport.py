"""Transport adapters: where Pia datagrams come from / go to.

ReplayTransport - OFFLINE. Replays a capture's IN datagrams (so the sim's whole RX stack runs
                  against the real host stream) and records the sim's OUT datagrams. Used by the
                  test harness; needs no hardware.

LiveTransport   - LIVE. Joins the FRLG console's LDN session with kinnay's `ldn` library (like
                  the bridge tooling), then moves UDP :12345 payloads on the 169.254.x interface
                  exactly as the bridge does: a bound UDP socket for TX (SO_BROADCAST)
                  and an AF_PACKET raw socket for RX (so subnet-directed broadcasts aren't dropped).
                  Requires root + the `netlink`/`ldn`/`trio` deps and the real Switch; it cannot be
                  exercised offline, so it is written to mirror the proven bridge code path.
"""

import base64
import json
import os
import pwd
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import traceback

ETH_P_IP = 0x0800
PROTO_UDP = 17
PIA_PORT = 12345
_MONITOR_IPC_LIMIT = 65536


_PIA_HDR = 0x5C     # Pia 6.16-6.41 LDN system header (sysCommVer 21/22); the game payload follows it


def _b85_decode(s):
    """Decode the custom base85 used for the RFU beacon payload: alphabet 0x23..0x78 skipping 0x5c
    ('\\'), first char = least-significant digit, 4-byte little-endian groups. len(s) is truncated to
    a multiple of 5."""
    out = bytearray()
    for i in range(0, len(s) - len(s) % 5, 5):
        v = 0
        for c in reversed(s[i:i + 5]):                  # reversed: first char is the LOW digit
            v = v * 85 + ((c - 0x23) if c < 0x5C else (c - 0x24))
        out += (v & 0xFFFFFFFF).to_bytes(4, "little")
    return bytes(out)


def _frlg_name(b):
    """Render a name from the FRLG character set (letters/digits) for the beacon dump."""
    out = []
    for x in b:
        if x == 0xFF:
            break
        if 0xBB <= x <= 0xD4:
            out.append(chr(ord("A") + x - 0xBB))
        elif 0xD5 <= x <= 0xEE:
            out.append(chr(ord("a") + x - 0xD5))
        elif 0xA1 <= x <= 0xAA:
            out.append(chr(ord("0") + x - 0xA1))
        else:
            out.append(" " if x == 0 else "?")
    return "".join(out).rstrip()


def _dump_beacon(app_data, log):
    """Dump the host's LDN advertisement application data (the RFU search beacon). It is a Pia
    6.16-6.41 system header (0x5C bytes: Switch nickname etc.) followed by the game payload, a
    custom-base85-encoded 24-byte RFU record (player trainer id, in-game name, RFU session id, partner
    info, game data). Diagnostics only - the connect id is not taken from here; it is a random nonzero
    value."""
    if not app_data:
        log("[live] beacon: NO application_data on the advertisement")
        return None
    app_data = bytes(app_data)
    log(f"[live] beacon application_data ({len(app_data)} B): {app_data.hex()}")
    if len(app_data) >= _PIA_HDR:
        gba = app_data[_PIA_HDR:]
        log(f"[live] beacon RFU payload (after the 0x5C Pia header, {len(gba)} B): {gba.hex()}")
        try:                                            # never let an odd beacon abort the join
            d = _b85_decode(gba)
            if len(d) >= 24:
                log(f"[live] beacon decoded: host name={_frlg_name(d[2:10])!r} "
                    f"TID=0x{int.from_bytes(d[0:2], 'little'):04x} "
                    f"RFU-session-id=0x{int.from_bytes(d[10:12], 'little'):04x} "
                    f"tradeSpecies={int.from_bytes(d[20:24], 'little') >> 16}")
        except Exception as e:
            log(f"[live] beacon decode skipped ({type(e).__name__}: {e})")
    return app_data


def _flatten_exc(e, depth=0):
    """Recursively flatten a (Base)ExceptionGroup - which is how trio reports failures from inside
    its nursery ('Exceptions from Trio nursery (N sub-exceptions)') - into the LEAF exceptions, so
    the real cause (e.g. a netlink/nl80211 EBUSY, an association timeout) is visible instead of the
    opaque group wrapper. Returns a list of (depth, exception) leaves."""
    subs = getattr(e, "exceptions", None)           # ExceptionGroup / trio.MultiError
    if subs:
        out = []
        for sub in subs:
            out.extend(_flatten_exc(sub, depth + 1))
        return out
    return [(depth, e)]


def _format_join_error(e):
    """Human-readable, fully-unwrapped description of an LDN-join failure, with the leaf exceptions'
    types, messages, and tracebacks (the opaque trio ExceptionGroup hides all of these)."""
    leaves = _flatten_exc(e)
    if len(leaves) == 1 and leaves[0][1] is e:      # not a group: report it directly
        leaf = e
        body = "".join(traceback.format_exception(type(leaf), leaf, leaf.__traceback__))
        return f"{type(leaf).__name__}: {leaf}\n{body}"
    parts = [f"{type(e).__name__} with {len(leaves)} underlying error(s):"]
    for i, (_d, leaf) in enumerate(leaves, 1):
        body = "".join(traceback.format_exception(type(leaf), leaf, leaf.__traceback__))
        parts.append(f"  [{i}] {type(leaf).__name__}: {leaf}\n{body}")
    return "\n".join(parts)


def _resolve_keys_path(path, environ=None, euid=None):
    """Resolve the caller's default keys path when Polkit has switched to root.

    ``pkexec`` exposes the original uid as ``PKEXEC_UID`` but changes ``HOME``
    to ``/root``.  Keep explicit absolute paths untouched and only use that uid
    for the documented ``~/.switch/prod.keys`` default.
    """
    environ = os.environ if environ is None else environ
    euid = os.geteuid() if euid is None else euid
    if path.startswith("~/") and euid == 0 and environ.get("PKEXEC_UID"):
        try:
            return os.path.join(pwd.getpwuid(int(environ["PKEXEC_UID"])).pw_dir, path[2:])
        except (KeyError, ValueError):
            pass
    return os.path.expanduser(path)

# LDN virtual interfaces to clear off the radio (ported from the bridge tooling).
LDN_VIFS = {"ldn", "ldn-mon", "ldn-tap", "ldnclient"}


# --- radio / interface cleanup (the library needs the radio free of stale vifs) -------------
def _run(cmd):
    subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _iw_del(iface):
    _run(["iw", "dev", iface, "del"])


def _sysctl(key, val):
    _run(["sysctl", "-wq", f"{key}={val}"])


def list_phy_ifaces():
    """Map phyName -> [netdev names] by parsing `iw dev`."""
    mapping, current = {}, None
    try:
        out = subprocess.check_output(["iw", "dev"], text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return mapping
    for raw in out.splitlines():
        s = raw.strip()
        if s.startswith("phy#"):
            current = "phy" + s[4:]
            mapping[current] = []
        elif s.startswith("Interface ") and current is not None:
            mapping[current].append(s.split()[1])
    return mapping


def free_radio(phys, log=print, preserve_ifaces=()):
    """Delete leftover LDN vifs and take other interfaces off the radio before a join.

    ``preserve_ifaces`` is an explicit diagnostic escape hatch for a concurrent
    monitor VIF (for example ``mon0``).  It never preserves an LDN-owned VIF,
    so stale ``ldnclient`` interfaces are still removed between attempts.
    """
    preserve_ifaces = set(preserve_ifaces) - LDN_VIFS
    mapping = list_phy_ifaces()
    for phy in {p for p in phys if p}:
        for iface in mapping.get(phy, []):
            if iface in LDN_VIFS:
                _iw_del(iface)
            elif iface in preserve_ifaces:
                log(f"[live] diagnostic: preserving {iface} ({phy})")
            else:
                _run(["nmcli", "device", "set", iface, "managed", "no"])
                _run(["ip", "link", "set", iface, "down"])
                log(f"[live] freed radio: brought {iface} ({phy}) down")
    # Belt-and-suspenders: a failed/abandoned join LEAKS its station vif (still associated to the
    # host), and `iw dev` may not map it under the expected phy - a leftover, still-associated
    # `ldnclient` then makes the NEXT association fail with nl80211 status code 1. Delete every
    # known LDN vif by name unconditionally so each join starts from a clean radio.
    for vif in LDN_VIFS:
        if vif in {i for ifs in mapping.values() for i in ifs} or _iface_exists(vif):
            _iw_del(vif)
            _run(["ip", "link", "del", vif])
            log(f"[live] freed radio: removed stale LDN vif {vif}")
    _run(["pkill", "-x", "wpa_supplicant"])
    time.sleep(0.3)


def _iface_exists(iface):
    import os
    return os.path.exists(f"/sys/class/net/{iface}")


def light_cleanup(log=print):
    """Delete the LDN virtual interfaces (teardown)."""
    for iface in sorted(LDN_VIFS):
        _iw_del(iface)
    time.sleep(0.3)


def tune_iface(iface, keep_ip, broadcast_ip, log=print):
    """Make the LDN interface deliver the host's link-local subnet broadcasts: relax rp_filter,
    force the 169.254.X.255 broadcast route into the local table, and drop stray zeroconf
    addresses that would shadow it (ported from the bridge tooling). Needs root."""
    _run(["nmcli", "device", "set", iface, "managed", "no"])
    _run(["pkill", "-f", f"avahi-autoipd.*{iface}"])
    for key in (f"net.ipv4.conf.{iface}.rp_filter", "net.ipv4.conf.all.rp_filter",
                "net.ipv4.conf.default.rp_filter"):
        _sysctl(key, "0")
    _sysctl(f"net.ipv4.conf.{iface}.accept_local", "1")
    _run(["ip", "route", "replace", "table", "local", "broadcast", broadcast_ip,
          "dev", iface, "proto", "static", "scope", "link", "src", keep_ip])
    try:
        out = subprocess.check_output(["ip", "-4", "addr", "show", "dev", iface],
                                      text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("inet "):
                cidr = line.split()[1]
                ip, _, prefix = cidr.partition("/")
                if ip != keep_ip and prefix != "24":
                    _run(["ip", "addr", "del", cidr, "dev", iface])
                    log(f"[live] removed stray address {cidr} from {iface}")
    except Exception as e:
        log(f"[live] stray-address cleanup skipped: {e}")

# The emulator's LDN passphrase (NintendoClients wiki "LDN Passphrases"). It belongs to the
# GBA emulator container, not the ROM, so it is SHARED across its titles: FRLG today, and
# Ruby/Sapphire/Emerald when they are re-released. It is ONE 64-byte value (the two 32-byte halves
# concatenate - earlier code mislabeled the second half as an "alternate"). Hardcoded as the
# default so no --password is needed.
GBA_APP_PASSPHRASE = bytes.fromhex(
    "fcb6f6adb9dfea66aca9c326149d2b3b08a781895cbf78f720d78b85a57584a9"
    "9665d237797b2a41ddef14063ec28d259143af7832fb3cbcf2759cbfbdc81d8c")
assert len(GBA_APP_PASSPHRASE) == 64


# ---------------------------------------------------------------------------
class ReplayTransport:
    """Offline: dispense capture IN datagrams; collect OUT datagrams the sim sends."""

    def __init__(self, in_datagrams, our_ip="169.254.21.2", host_ip="169.254.21.1"):
        # in_datagrams: list of (payload_bytes, src_ip_str), in capture order
        self._in = list(in_datagrams)
        self._i = 0
        self.our_ip = our_ip
        self.host_ip = host_ip
        self.sent = []                  # [(datagram, dst_ip)]
        self.batch = 4                  # IN datagrams handed out per recv() (coalescing model)

    def recv(self):
        out = []
        for _ in range(self.batch):
            if self._i >= len(self._in):
                break
            out.append(self._in[self._i])
            self._i += 1
        return out

    def send(self, datagram, dst_ip):
        self.sent.append((datagram, dst_ip))

    @property
    def drained(self):
        return self._i >= len(self._in)

    @classmethod
    def from_capture(cls, raw_path):
        """Load a raw capture: IN datagrams + session ssid/ips."""
        metas, ins = [], []
        sess = {}
        for line in open(raw_path, errors="replace"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("rec") == "meta":
                if r.get("event") == "session":
                    sess = r
                continue
            if r.get("rec") == "pkt" and r.get("dir") == "in":
                ins.append((bytes.fromhex(r["hex"]), r["src"].rsplit(":", 1)[0]))
        t = cls(ins, our_ip=sess.get("ip", "169.254.21.2"),
                host_ip=sess.get("ip", "169.254.21.1").rsplit(".", 1)[0] + ".1")
        t.ssid = bytes.fromhex(sess["ssid_hex"]) if sess.get("ssid_hex") else None
        return t


# ---------------------------------------------------------------------------
class MonitorHelperError(RuntimeError):
    """The separate AX200 monitor helper could not provide a safe IPC stream."""


class _MonitorAdvertisementSource:
    """Strict line-delimited JSON reader passed to the vendored LDN fork."""

    def __init__(self, stream):
        self._stream = stream
        self._buffer = bytearray()
        self.received = 0
        self.stats = None

    async def _message(self):
        while b"\n" not in self._buffer:
            chunk = await self._stream.receive_some(_MONITOR_IPC_LIMIT)
            if not chunk:
                raise MonitorHelperError("monitor helper disconnected")
            self._buffer.extend(chunk)
            if len(self._buffer) > _MONITOR_IPC_LIMIT:
                raise MonitorHelperError("monitor helper sent an oversized message")
        raw, _, rest = self._buffer.partition(b"\n")
        self._buffer = bytearray(rest)
        if not raw or len(raw) > _MONITOR_IPC_LIMIT:
            raise MonitorHelperError("monitor helper sent an invalid message length")
        try:
            message = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise MonitorHelperError("monitor helper sent invalid JSON") from e
        if not isinstance(message, dict) or message.get("version") != 1:
            raise MonitorHelperError("monitor helper sent an unsupported message")
        return message

    async def expect_ready(self):
        message = await self._message()
        if message != {"version": 1, "type": "ready"}:
            raise MonitorHelperError("monitor helper did not send ready")

    async def receive_advertisement(self):
        while True:
            message = await self._message()
            if message.get("type") == "stats":
                self._set_stats(message)
                continue
            if message.get("type") == "advertisement":
                break
            raise MonitorHelperError("monitor helper sent an unexpected message")
        source = message.get("source")
        frequency = message.get("frequency")
        action = message.get("action")
        if not isinstance(source, str) or len(source) != 12:
            raise MonitorHelperError("monitor helper sent an invalid source")
        if not isinstance(frequency, int) or frequency <= 0:
            raise MonitorHelperError("monitor helper sent an invalid frequency")
        if not isinstance(action, str):
            raise MonitorHelperError("monitor helper sent an invalid action")
        try:
            source_bytes = bytes.fromhex(source)
            action_bytes = base64.b64decode(action, validate=True)
        except ValueError as e:
            raise MonitorHelperError("monitor helper sent malformed advertisement data") from e
        if len(source_bytes) != 6 or not action_bytes:
            raise MonitorHelperError("monitor helper sent malformed advertisement fields")
        self.received += 1
        return source_bytes, frequency, action_bytes

    def _set_stats(self, message):
        phase = message.get("phase")
        fields = ("raw", "radiotap", "action", "vendor", "advertisement")
        if phase not in {"pre-join", "authorized"}:
            raise MonitorHelperError("monitor helper sent an invalid stats phase")
        stats = {field: message.get(field) for field in fields}
        if any(not isinstance(value, int) or value < 0 for value in stats.values()):
            raise MonitorHelperError("monitor helper sent invalid stats")
        self.stats = {"phase": phase, **stats}

    async def mark_authorized(self):
        await self._stream.send_all(
            b'{"version":1,"type":"mark","phase":"authorized"}\n'
        )

    async def aclose(self):
        await self._stream.aclose()


class _MonitorHelper:
    """Own a private Unix listener and the process feeding its LDN stream."""

    def __init__(self, ifname, keys_path):
        self.ifname = ifname
        self.keys_path = _resolve_keys_path(keys_path)
        self.runtime_dir = None
        self.listener = None
        self.process = None
        self.source = None

    async def start(self):
        import trio

        self.runtime_dir = tempfile.mkdtemp(prefix="frlg-ldn-monitor-")
        os.chmod(self.runtime_dir, 0o700)
        socket_path = os.path.join(self.runtime_dir, "monitor.sock")
        self.listener = trio.socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        await self.listener.bind(socket_path)
        self.listener.listen(1)

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        child_env = os.environ.copy()
        old_path = child_env.get("PYTHONPATH", "")
        child_env["PYTHONPATH"] = project_root + (os.pathsep + old_path if old_path else "")
        command = [sys.executable, "-m", "frlgsim.monitor_helper", "--socket", socket_path,
                   "--iface", self.ifname, "--keys", self.keys_path]
        self.process = await trio.lowlevel.open_process(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, cwd=project_root, env=child_env,
        )

        client = None
        with trio.move_on_after(5) as scope:
            client, _ = await self.listener.accept()
        if scope.cancelled_caught or client is None:
            raise MonitorHelperError("monitor helper did not connect within 5 seconds")
        try:
            _pid, uid, _gid = struct.unpack("3i", client.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, 12
            ))
        except OSError as e:
            client.close()
            raise MonitorHelperError("could not verify monitor helper peer") from e
        if uid != os.geteuid():
            client.close()
            raise MonitorHelperError("monitor helper peer has an unexpected uid")
        self.source = _MonitorAdvertisementSource(trio.SocketStream(client))
        with trio.move_on_after(5) as scope:
            await self.source.expect_ready()
        if scope.cancelled_caught:
            raise MonitorHelperError("monitor helper did not become ready within 5 seconds")
        return self.source

    async def aclose(self):
        if self.source is not None:
            await self.source.aclose()
            self.source = None
        if self.listener is not None:
            self.listener.close()
            self.listener = None
        if self.process is not None and self.process.returncode is None:
            self.process.terminate()
            import trio
            with trio.move_on_after(2) as scope:
                await self.process.wait()
            if scope.cancelled_caught and self.process.returncode is None:
                self.process.kill()
                await self.process.wait()
        self.process = None
        if self.runtime_dir is not None:
            shutil.rmtree(self.runtime_dir, ignore_errors=True)
            self.runtime_dir = None


async def _scan_from_monitor_source(
    ldn, keys, source, ifname, channels=(1, 6, 11), dwell_time=1.0
):
    """Decode scan candidates from the already-running AX200 monitor helper.

    Creating LDN's normal scan monitor beside ``mon0`` changes the receive set
    on this adapter.  Reuse the IPC stream instead, then leave the same source
    attached to ``STANetwork`` for the post-association advertisement.  Unlike
    a normal ``ldn.scan()``, an existing monitor VIF does not hop channels by
    itself, so explicitly sweep the standard LDN channels before connecting.
    """
    import trio
    from ldn import wlan

    derivations = {
        protocol: ldn.KeyDerivation(keys, protocol) for protocol in (1, 3)
    }
    networks = []
    addresses = set()
    for channel in channels:
        result = await trio.run_process(
            ["/usr/sbin/iw", "dev", ifname, "set", "channel", str(channel)],
            capture_stdout=True, capture_stderr=True, check=False,
        )
        if result.returncode:
            raise MonitorHelperError(
                f"could not tune monitor interface {ifname} to channel {channel}"
            )
        with trio.move_on_after(dwell_time):
            while True:
                source_address, frequency, action = await source.receive_advertisement()
                for protocol, derivation in derivations.items():
                    frame = ldn.AdvertisementFrame(derivation, protocol)
                    try:
                        frame.decode(action)
                    except Exception:
                        continue
                    info = ldn.NetworkInfo(protocol)
                    info.address = ldn.MACAddress(source_address)
                    info.channel = wlan.map_frequency(frequency)
                    info.band = ldn.ChannelBands[info.channel]
                    info.parse_advertisement(frame)
                    if info.address not in addresses:
                        addresses.add(info.address)
                        networks.append(info)
                    break
    return networks


# ---------------------------------------------------------------------------
class LiveTransport:
    """Join the console's LDN session and exchange UDP :12345 datagrams. Mirrors the bridge
    (scan/connect + UDP TX socket + AF_PACKET RX). Untested offline."""

    # FRLG LDN identity (the same the bridge/console use).
    LOCAL_COMMUNICATION_ID = 0x0100610011000000     # FireRed/LeafGreen emulator title id
    SCENE_ID = 0
    APPLICATION_VERSION = 1

    def __init__(self, password=None, nickname="EMU", keys_path="~/.switch/prod.keys",
                 local_comm_id=None, scene_id=None, app_version=None,
                 phyname="phy0", ifname="ldnclient", log=print, preserve_ifaces=(),
                 monitor_ifname=None, preconnect_scan=None):
        self.info = getattr(log, "info", log)   # clean milestone sink (default-mode narration)
        self.password = password if password else GBA_APP_PASSPHRASE
        self.nickname = nickname
        self.keys_path = _resolve_keys_path(keys_path)
        self.phyname = phyname
        self.ifname = ifname
        self.preserve_ifaces = tuple(preserve_ifaces)
        self.monitor_ifname = monitor_ifname
        self.preconnect_scan = (
            monitor_ifname is not None if preconnect_scan is None else preconnect_scan
        )
        if local_comm_id is not None:
            self.LOCAL_COMMUNICATION_ID = local_comm_id
        if scene_id is not None:
            self.SCENE_ID = scene_id
        if app_version is not None:
            self.APPLICATION_VERSION = app_version
        self.log = log
        self.ssid = None
        self.our_ip = None
        self.host_ip = None
        self.our_mac = None        # our 6-byte LDN MAC = our Pia connection GUID (constant id)
        self.host_mac = None       # the host's 6-byte LDN MAC = its Pia connection GUID
        self.app_data = None       # the host's LDN advertisement beacon (emulator RFU search data)
        self.iface = None
        self.broadcast = None
        self._tx = None
        self._rx = None
        self._rx_seen = 0
        self._thread = None
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._err = None

    # -- LDN join runs in a trio thread that keeps the connection alive -------
    def start(self, timeout=None, attempts=3, settle=1.5):
        """Join the LDN network, retrying transient failures. The LDN/nl80211 layer flakes
        intermittently (radio busy, association timeout, a stale vif racing the fresh join) - the
        SAME failure the bridge hits as 'connection failed'. Rather than make the user re-run, we
        free the radio and retry up to `attempts` times, logging each attempt's FULLY-UNWRAPPED
        cause (see _format_join_error) so persistent problems are still diagnosable instead of
        hidden behind trio's opaque ExceptionGroup."""
        if timeout is None:
            timeout = 60 if self.monitor_ifname is not None else 30
        last_err = None
        for attempt in range(1, attempts + 1):
            preserve_ifaces = self.preserve_ifaces
            if self.monitor_ifname is not None:
                preserve_ifaces += (self.monitor_ifname,)
            free_radio({self.phyname}, self.log, preserve_ifaces)
            self._err = None
            self._ready.clear()
            self._stop.clear()
            self._thread = threading.Thread(target=self._run_ldn, daemon=True)
            self._thread.start()
            if not self._ready.wait(timeout):
                last_err = f"LDN join timed out after {timeout}s (attempt {attempt}/{attempts})"
                self.log(f"[live] {last_err}")
                self._stop.set()                        # ask the (stuck) attempt to unwind
            elif self._err:
                last_err = self._err                    # already unwrapped + logged in _run_ldn
            else:
                tune_iface(self.iface, self.our_ip, self.broadcast, self.log)  # host broadcasts
                self._setup_sockets()
                if attempt > 1:
                    self.log(f"[live] LDN join succeeded on attempt {attempt}/{attempts}.")
                return self
            self._stop.set()
            if self._thread is not None:
                self._thread.join(timeout=2)            # let an abandoned attempt unwind/disconnect
            if attempt < attempts:
                self.log(f"[live] retrying LDN join in {settle}s "
                         f"(attempt {attempt + 1}/{attempts})...")
                time.sleep(settle)                      # let the radio settle before retrying
        light_cleanup(self.log)                         # remove any vif a failed attempt leaked
        raise RuntimeError(f"LDN join failed after {attempts} attempt(s):\n{last_err}")

    def _run_ldn(self):
        try:
            import trio
            import ldn
        except ImportError as e:                     # pragma: no cover
            self._err = f"missing dep for live mode: {e}"
            self._ready.set()
            return

        async def main():
            keys = ldn.load_keys(self.keys_path)
            helper = None
            if self.monitor_ifname is not None:
                helper = _MonitorHelper(self.monitor_ifname, self.keys_path)
                try:
                    await helper.start()
                except BaseException:
                    await helper.aclose()
                    raise
            self.info("Scanning for the FRLG network...")
            try:
                if helper is not None:
                    networks = await _scan_from_monitor_source(
                        ldn, keys, helper.source, self.monitor_ifname
                    )
                else:
                    networks = await ldn.scan(keys, phyname=self.phyname)
            except BaseException:
                if helper is not None:
                    await helper.aclose()
                raise
            joinable = [n for n in networks
                        if n.accept_policy != ldn.ACCEPT_NONE
                        and n.num_participants < n.max_participants]
            for n in networks:
                # also log accept_policy: a blacklist/whitelist host (policy != ACCEPT_ALL) passes the
                # joinable filter but then rejects our auth, surfacing as an opaque trio timeout - logging
                # it makes "this Switch isn't accepting this MAC" diagnosable.
                self.log(f"[live] saw network comm_id=0x{n.local_communication_id:016x} "
                         f"scene={n.scene_id} {n.num_participants}/{n.max_participants} "
                         f"accept_policy={getattr(n, 'accept_policy', '?')}")
            # Prefer an exact FRLG comm-id match; else fall back to the only joinable network.
            net = next((n for n in joinable
                        if n.local_communication_id == self.LOCAL_COMMUNICATION_ID), None)
            if net is None and len(joinable) == 1:
                net = joinable[0]
                self.log(f"[live] no comm-id match; using the only joinable network "
                         f"(comm_id=0x{net.local_communication_id:016x})")
            if net is None:
                self._err = (f"no joinable FRLG network (saw {len(networks)}, "
                             f"{len(joinable)} joinable) - set --comm-id from the list above")
                if helper is not None:
                    await helper.aclose()
                self._ready.set()
                return
            self.LOCAL_COMMUNICATION_ID = net.local_communication_id
            # The advertisement's application data is the RFU search beacon (dumped + decoded for
            # diagnostics). The connect id is not taken from here: any nonzero value works, so it is a
            # random nonzero value chosen locally.
            self.app_data = _dump_beacon(getattr(net, "application_data", b"") or b"", self.log)
            param = ldn.ConnectNetworkParam()
            param.keys = keys
            param.network = net
            param.password = self.password           # 64-byte emulator passphrase
            param.name = self.nickname.encode()
            param.app_version = self.APPLICATION_VERSION
            param.phyname = self.phyname              # wifi phy (like the bridge: phy0)
            param.ifname = self.ifname                # station iface (like the bridge: ldnclient)
            param.diagnostic = lambda stage: self.log(f"[live] ldn stage={stage}")
            param.preconnect_scan = self.preconnect_scan
            param.infer_address_on_timeout = self.monitor_ifname is not None
            try:
                if self.monitor_ifname is not None:
                    param.advertisement_source = helper.source
                self.info("Joining the host...")
                async with ldn.connect(param) as network:
                    info = network.info()
                    self.ssid = info.ssid
                    self.iface = self.ifname
                    # The host is participant 0 (the network creator); its IP fixes the 169.254.X subnet.
                    parts = list(getattr(info, "participants", []) or [])
                    host = parts[0] if parts else None
                    self.host_ip = host.ip_address if host else "169.254.21.1"
                    self.host_mac = bytes(host.mac_address) if host else b"\x00" * 6
                    ours = next((p for p in parts if p is not host and self._pname(p) == self.nickname),
                                None) or next((p for p in parts if p is not host
                                               and getattr(p, "connected", False)), None)
                    self.our_ip = (self._iface_ip() or (ours.ip_address if ours else None)
                                   or self.host_ip.rsplit(".", 1)[0] + ".2")
                    self.our_mac = ((bytes(ours.mac_address) if ours else None)
                                    or self._iface_mac() or b"\x00" * 6)
                    self.broadcast = self.our_ip.rsplit(".", 1)[0] + ".255"
                    self.log(f"[live] joined ssid={self.ssid.hex()} "
                             f"us={self.our_ip}/{self.our_mac.hex()} "
                             f"host={self.host_ip}/{self.host_mac.hex()}")
                    self.info("Joined.")
                    self._ready.set()
                    while not self._stop.is_set():
                        await trio.sleep(0.2)
            finally:
                if helper is not None:
                    await helper.aclose()

        async def main_with_stop():
            async def stop_watcher(cancel_scope):
                while not self._stop.is_set():
                    await trio.sleep(.1)
                self._err = "LDN join cancelled after caller timeout"
                cancel_scope.cancel()

            async with trio.open_nursery() as nursery:
                nursery.start_soon(stop_watcher, nursery.cancel_scope)
                await main()
                nursery.cancel_scope.cancel()

        try:
            trio.run(main_with_stop)
        except BaseException as e:                     # pragma: no cover
            # trio wraps nursery failures in a (Base)ExceptionGroup whose str() is the useless
            # "Exceptions from Trio nursery (N sub-exceptions)"; unwrap to the real leaf cause(s).
            self._err = _format_join_error(e)
            self.log(f"[live] LDN join FAILED:\n{self._err}")
            self._ready.set()

    @staticmethod
    def _pname(p):
        try:
            return p.name.decode("utf-8", "replace").rstrip("\0")
        except Exception:
            return ""

    def _iface_mac(self):
        """Read the station interface's MAC as a last-resort fallback for our connection GUID."""
        try:
            with open(f"/sys/class/net/{self.ifname}/address") as f:
                return bytes.fromhex(f.read().strip().replace(":", ""))
        except OSError:
            return None

    def _iface_ip(self):
        """Read the IPv4 the ldn lib actually assigned to the station iface (ground truth)."""
        try:
            out = subprocess.check_output(["ip", "-4", "-o", "addr", "show", "dev", self.ifname],
                                          text=True, stderr=subprocess.DEVNULL)
            for line in out.splitlines():
                parts = line.split()
                if "inet" in parts:
                    ip = parts[parts.index("inet") + 1].split("/")[0]
                    if ip.startswith("169.254."):
                        return ip
        except Exception:
            pass
        return None

    def _setup_sockets(self):
        tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        tx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tx.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        tx.bind(("0.0.0.0", PIA_PORT))
        self._tx = tx
        rx = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_IP))
        rx.bind((self.iface, 0))
        rx.setblocking(False)
        # Grow the kernel receive buffer so a burst of host frames between our ~60Hz recv() drains is
        # not dropped at the OS level (AF_PACKET ring overflow shows up as silent gaps in the reliable
        # stream -> recovery work; cutting OS drops cuts the recovery we depend on). Best-effort: the
        # kernel clamps to net.core.rmem_max, so log what we actually got. 8 MiB request.
        try:
            rx.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
            got = rx.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
            self.log(f"[live] rx socket SO_RCVBUF = {got} bytes "
                     f"(raise net.core.rmem_max if lower than requested 8 MiB)")
        except OSError as e:
            self.log(f"[live] could not enlarge rx SO_RCVBUF: {e}")
        self._rx = rx

    # -- data plane ----------------------------------------------------------
    def send(self, datagram, dst_ip):
        dst = self.broadcast if dst_ip in (self.broadcast, "255.255.255.255") else dst_ip
        try:
            self._tx.sendto(datagram, (dst, PIA_PORT))
        except OSError as e:
            self.log(f"[live] sendto failed: {e}")

    def _accept_dst(self, dst_ip):
        """The host INITIATES by BROADCASTING its Net 0x11 to the subnet .255 (the reference capture seq 1 ->
        169.254.X.255), then unicasts to us. Accept our own IP, ANY 169.254.*.255 link-local
        broadcast (robust to imperfect subnet resolution), and the global broadcasts - so we never
        miss the host's broadcast outreach."""
        return (dst_ip == self.our_ip
                or (dst_ip.startswith("169.254.") and dst_ip.endswith(".255"))
                or dst_ip in ("255.255.255.255",))

    def recv(self):
        out = []
        if self._rx is None:
            return out
        while True:
            try:
                data = self._rx.recv(65535)
            except (BlockingIOError, OSError):
                break
            parsed = self._parse_udp(data)
            if parsed is None:
                continue
            src_ip, src_port, dst_ip, dst_port, payload = parsed
            if src_ip == self.our_ip or dst_port != PIA_PORT or not self._accept_dst(dst_ip):
                continue
            self._rx_seen += 1
            if self._rx_seen <= 10:
                self.log(f"[live] RX #{self._rx_seen}: {src_ip} -> {dst_ip}:{dst_port} "
                         f"len={len(payload)} {payload[:4].hex()}")
            out.append((payload, src_ip))
        return out

    @staticmethod
    def _parse_udp(frame):
        if len(frame) < 14 + 20 + 8 or struct.unpack_from("!H", frame, 12)[0] != ETH_P_IP:
            return None
        ip = frame[14:]
        if (ip[0] >> 4) != 4 or ip[9] != PROTO_UDP:
            return None
        ihl = (ip[0] & 0x0F) * 4
        src_ip = socket.inet_ntoa(ip[12:16])
        dst_ip = socket.inet_ntoa(ip[16:20])
        udp = ip[ihl:]
        if len(udp) < 8:
            return None
        src_port, dst_port, ulen = struct.unpack_from("!HHH", udp, 0)
        payload = udp[8:][:max(0, ulen - 8)] if ulen >= 8 else udp[8:]
        return src_ip, src_port, dst_ip, dst_port, payload

    def stop(self):
        self._stop.set()
        for s in (self._tx, self._rx):
            try:
                if s:
                    s.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2)
        light_cleanup(self.log)                         # delete the LDN vifs on teardown
