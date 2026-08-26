# Baseline reproductible et environnement

[← Retour à l’index du dossier](index.md)

Cette page décrit les informations à figer avant une expérience et les
précautions de confidentialité associées. Les résultats eux-mêmes sont dans le
[journal d’expériences](experiments.md).

## Figer le baseline

Créer une branche de travail et noter les versions exactes. Pour un fork
GitHub, conserver idéalement `upstream` pour `tornadus/frlg-ldn-trade` et
utiliser `origin` pour le fork personnel.

```bash
git status --short --branch
git rev-parse HEAD
uname -a
sudo ethtool -i wlan0
iw phy
./venv/bin/python -m pip freeze
```

Ne jamais archiver les clés, les Pokémon, les MAC, le SSID ou les noms visibles
dans les annonces.

## Environnement de reproduction connu

Référence communiquée le 2026-08-26 :

- Distribution : CachyOS (Arch rolling).
- Noyau : `7.2.0-1-cachyos`.
- Carte : Intel Wi-Fi 6 AX200, PCI `8086:2723`, sous-système `8086:0084`.
- Pilote : `iwlwifi` ; op-mode : `iwlmvm`.
- Firmware : `77.aa2dd297.0 cc-a0-77.ucode`.
- Le mode monitor est annoncé.
- `power_scheme=1` (CAM/actif) n’a pas changé l’échec.

Les détails techniques et les limites d’interprétation sont regroupés dans
[findings.md](findings.md).

## Révisions locales à identifier

Pour chaque essai, consigner au minimum :

- commit de l’application ;
- révision ou chemin du fork `vendor/ldn` ;
- version du noyau et du firmware ;
- version de `ldn`/`python-netlink` ;
- carte de contrôle utilisée, si applicable.

Ne pas inclure dans Git les fichiers `prod.keys`, `.pk3`, `.ek3`, les captures
PCAP, les adresses MAC, les SSID, les noms de dresseur ou les logs verbeux
complets. Les artefacts bruts restent locaux et doivent être redacted avant
partage.
