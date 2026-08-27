# frlg-ldn-trade

A proof-of-concept demonstrating that it is indeed possible for a computer to interact with Gen 3 Pokémon games running on Switch/Switch 2 via local wireless (LDN).

---

## Why?

This project basically exists to prove that it can be done. From here, I'm hoping the community takes notice so that we can get things like an unofficial GTS and online battling going. It should serve as a pretty good reference for anyone interested in pursuing these goals or anything else related to multiplayer within these games. And before you ask, yes, **AI tools were used extensively during the creation of this project**. Difficult to call it "vibe coding" though, Claude required A LOT of steering and was basically lost without me laying out the path forward step-by-step. The main benefit was massively speeding up the reverse engineering work. If you'd like to contribute to the effort, join the [Discord!](https://discord.gg/PyvaVYnpXC)

## Demonstration
https://github.com/user-attachments/assets/b0df878e-67f0-483d-ae81-583cfc2a8692

This demo was recorded using the **ALFA AWUS036ACHM**. The RZ616 is half as fast on average and sometimes deadlocks before gracefully exiting.

## Features

- End-to-end trading with a real game running on a real Switch
- .pk3/.ek3 input and output

## Requirements
- Linux
- Python 3.12+, and a venv with requirements installed (see requirements.txt)
- a compatible WiFi card (see below)
- A Switch or Switch 2 with FRLG, played to the point where the Direct Corner has been unlocked (~20-40 minutes)
- At least 2 .pk3 files to serve as simulated party members/trade fodder
- Switch prod.keys (the default location is ``~/.switch/prod.keys``)

### Tested WiFi Cards

| Model            | Type           | Driver  | Reliability  |
|------------------|----------------|---------|--------------|
| AMD RZ616        | Internal (M.2) | mt7921e | Low          |
| ALFA AWUS036ACHM | External       | mt76x0u | High         |
| Realtek RTL8821CE | Internal (PCIe 1x) | rtw88_8821ce | High |
| Intel AX200 | Internal (M.2) | iwlwifi/iwlmvm | Experimental: one complete trade with monitor workaround |

### Known Problematic WiFi Cards

| Model            | Type           | Driver  | Issue        |
|------------------|----------------|---------|--------------|
| Atheros AR9271 | External       | ath9k_htc | Unable to be assigned ip (most of the time) |

See the [Intel AX200 support dossier](docs/ax200-support/index.md) for the
current diagnosis, experiments, and live-acceptance criteria.

### Experimental Intel AX200 path

On 2026-08-27 an AX200 completed one real end-to-end trade, including a valid
100-byte output `.pk3` and a clean RFU disconnect. This is not yet considered a
fully validated fix: two more AX200 repetitions and a regression check with a
known-good adapter are still required. The station still misses the
post-authorization LDN advertisement, so the workaround uses a tightly guarded
`.2` address inference after a timeout.

The AX200 path needs an existing monitor interface and the explicit
`--monitor-iface` flag. It also performs a managed pre-connect scan to populate
the AX200 BSS cache. These behaviors are not enabled for the normal adapter
path.

```bash
pkexec systemctl stop NetworkManager
pkexec iw phy phy0 interface add mon0 type monitor
pkexec ip link set mon0 up

pkexec env PYTHONUNBUFFERED=1 PYTHONPATH="$PWD" \
  "$PWD/venv/bin/python" "$PWD/frlgtrade.py" \
  --live --verbose --phy phy0 --monitor-iface mon0 \
  --keys /absolute/path/to/prod.keys \
  -o "$PWD/output.pk3" "$PWD/PARTY1.pk3" "$PWD/PARTY2.pk3"
```

Before every retry, ensure that no privileged client from an earlier `pkexec`
run is still alive. An interrupted parent shell may leave its root child
running; multiple clients can poison the current Switch lobby. Kill stale
clients, delete `ldnclient`, and recreate the Leader lobby before retrying.
The exact checks, milestones and rollback commands are in the
[AX200 hardware procedure](docs/ax200-support/procedure.md); the first success
is documented in [its full report](docs/ax200-support/first-success.md).

## Usage

```bash
pkexec env PYTHONPATH="$PWD" \
  "$PWD/venv/bin/python" "$PWD/frlgtrade.py" \
  --live -o "$PWD/output.pk3" "$PWD/PARTY1.pk3" "$PWD/PARTY2.pk3"
```

**Optional Flags (not comprehensive):**

| Flag         | Options          | Purpose        |
|--------------|------------------|----------------|
| --verbose    | N/A              | Verbose output  |
| --phy        | phy# (e.g. phy1)  | WiFi phy selection |
| --keys       | /path/to/prod.keys | non-default prod.keys location |
| --monitor-iface | interface (e.g. mon0) | explicit experimental monitor helper, required for current AX200 workaround |

Above is the configuration I suggest using if you'd like a quick and easy demonstration of the program. You can use any of the listed optional flags, they're safe. Many of the undocumented ones are either unfinished, untested, internal tools, or artifacts of experiments that did not/have not yet panned out.

**Setup**
1. Create a Python venv and install all requirements in ``requirements.txt``
2. Ensure your WiFi card is unmanaged. The easiest way to accomplish this is stopping NetworkManager.
3. Ensure you can become root. The script requires root to run.

**Step-by-step Usage**
1. Select trading at the direct corner and make your console the "Leader".
2. Run the script. It may take multiple times to successfully connect.
3. Wait for "EMU" to join and for both players to enter the trading room.
4. Walk to the LEFT CHAIR in the trading room. Walking may be laggy.
5. Select the Pokémon you'd like to trade away.
6. Accept the trade confirmation. You will be traded the *2nd* simulated party member.
7. Once you return to the trade menu, cancel the trade.
8. Walk out.
9. You'll find PARTY2.pk3 in your party, and the Pokémon you traded will be in pwd as output.pk3 (or whatever you called it). 

After the run, restore your network manager and remove temporary LDN/monitor
interfaces. AX200 users should follow the exact cleanup in the
[hardware procedure](docs/ax200-support/procedure.md), including checking for
privileged child processes left behind by an interrupted `pkexec` command.
 
## Credits
- [kinnay](https://github.com/kinnay) - For the [LDN library](https://github.com/kinnay/LDN) this is built upon, and the excellent [NintendoClients Wiki](https://github.com/kinnay/NintendoClients/wiki)
- [pokefirered](https://github.com/pret/pokefirered) - A full decompilation of FireRed/LeafGreen, including the Switch port. It served as an important reference.

## License
AGPLv3
