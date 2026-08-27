# Agent guide

## Mission

Maintain a fork of `tornadus/frlg-ldn-trade` whose live LDN join works with an
Intel AX200 on Linux. Preserve compatibility with the Wi-Fi adapters already
listed as working in `README.md`.

Before AX200-related work, read the AX200 dossier starting with
[`docs/ax200-support/index.md`](docs/ax200-support/index.md), then read the
linked pages relevant to the experiment in full. It is the durable handoff:
the pages record the reproduced failure, known facts, open hypotheses,
experiment order, and evidence to capture.

## Repository map

- `frlgtrade.py`: CLI and live/replay entry points.
- `frlgsim/transport.py`: wraps the external `ldn` package for scan, join, and
  post-join networking. This is the main repository-side integration surface.
- `requirements.txt`: targets `ldn==0.0.17` through the reproducible editable
  fork in `vendor/ldn`; `python-netlink` remains an installed dependency.
- `docs/ax200-support/index.md`: AX200 dossier entry point and current status.
- `docs/ax200-support/findings.md`: verified facts, evidence, and hypotheses.
- `docs/ax200-support/first-success.md`: reproducible report and timeline for
  the first complete AX200 trade on 2026-08-27.
- `docs/ax200-support/baseline.md`: reproducible environment and safeguards.
- `docs/ax200-support/procedure.md`: hardware procedure and acceptance checks.
- `docs/ax200-support/decisions.md`: experiment decision tree and fix surfaces.
- `docs/ax200-support/experiments.md`: append-only experiment log.
- `docs/ax200-support/references.md`: primary sources and code points.

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
- Update `docs/ax200-support/experiments.md` after every hardware experiment
  with date, exact kernel/firmware/package revisions, command, result, and
  conclusion; update the relevant dossier page when the current status or
  procedure changes.

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

The repository has a small monitor-helper IPC unittest module, but no complete
automated trade suite. Live AX200 acceptance requires the hardware procedure
in `docs/ax200-support/procedure.md`; never claim the issue fixed from offline
checks alone. One complete trade succeeded on 2026-08-27; two further AX200
runs and a known-good-adapter control are still required.
