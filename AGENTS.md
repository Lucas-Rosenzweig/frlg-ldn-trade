# Agent guide

## Mission

Maintain a fork of `tornadus/frlg-ldn-trade` whose live LDN join works with an
Intel AX200 on Linux. Preserve compatibility with the Wi-Fi adapters already
listed as working in `README.md`.

Before AX200-related work, read [`docs/ax200-support.md`](docs/ax200-support.md)
in full. It is the durable handoff: it records the reproduced failure, known
facts, open hypotheses, experiment order, and evidence to capture.

## Repository map

- `frlgtrade.py`: CLI and live/replay entry points.
- `frlgsim/transport.py`: wraps the external `ldn` package for scan, join, and
  post-join networking. This is the main repository-side integration surface.
- `requirements.txt`: pins `ldn==0.0.17`; `ldn` and `python-netlink` are
  installed dependencies, not vendored source.
- `docs/ax200-support.md`: AX200 investigation log and decision record.

## Working rules

- Treat the AX200 root cause as unproven until a simultaneous managed + monitor
  capture establishes where broadcast Action Frames stop.
- Keep observations, hypotheses, and conclusions explicitly separated.
- Prefer the smallest falsifiable experiment. Do not start by rewriting a
  driver or blindly advertising a kernel capability.
- Do not edit files under `venv/` as the product fix. Prototype dependency
  changes in a reproducible patch, fork, or vendored source tree.
- Preserve a control path for a known-good adapter when changing generic LDN
  behavior.
- Never commit `prod.keys`, `.pk3`/`.ek3` files, packet captures, MAC addresses,
  SSIDs, trainer names, or full verbose logs. Redact captured artifacts before
  sharing them.
- Kernel/module experiments must retain a known-good boot entry and include
  unload/rollback instructions. Do not replace the only working kernel.
- Update `docs/ax200-support.md` after every hardware experiment with date,
  exact kernel/firmware/package revisions, command, result, and conclusion.

## Minimum verification

For documentation-only changes:

```bash
git diff --check
```

For Python changes:

```bash
./venv/bin/python -m compileall -q frlgtrade.py frlgsim
./venv/bin/python frlgtrade.py --help >/dev/null
```

There is no committed automated test suite. Live AX200 acceptance requires the
hardware procedure in `docs/ax200-support.md`; never claim the issue fixed from
offline checks alone.
