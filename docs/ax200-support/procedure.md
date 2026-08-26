# Procédure hardware, validation et nettoyage

[← Retour à l’index du dossier](index.md)

## Probe monitor userspace

Le probe versionné est `tools/ax200_monitor_probe.py`. Il s’attache à une VIF
monitor existante, décode les advertisements avec les classes LDN installées
et ne produit qu’un compteur agrégé. L’exécuter pendant le join avec :

```bash
pkexec ./venv/bin/python tools/ax200_monitor_probe.py \
  --iface mon0 --keys /chemin/absolu/vers/prod.keys --duration 12
```

## Helper monitor intégré

`--monitor-iface mon0` lance automatiquement un helper séparé avant
l’association. Le helper utilise une socket Unix privée et s’arrête avec la
tentative de join ; il n’existe aucun fallback silencieux vers la réception
station si le helper échoue. La VIF monitor doit déjà exister sur le même PHY.

Pour le scénario actuel, lancer le join sous `pkexec` ; ne pas employer `sudo`
dans les commandes de reprise :

```bash
pkexec env PYTHONPATH="$PWD" ./venv/bin/python frlgtrade.py \
  --live --verbose --phy phy1 --monitor-iface mon0 \
  -o output.pk3 PARTY1.pk3 PARTY2.pk3
```

Le helper doit être prêt avant le scan. Le timeout à 10 secondes avec le helper
est un résultat de diagnostic, pas une preuve de succès : sur les essais du
2026-08-27, les advertisements IPC étaient revalidées mais ne contenaient pas
le participant local, sans adresse IP et sans erreur affichée par la Switch,
qui restait en attente.

## Étape 0 — préparer une expérience contrôlée

Consulter le [baseline reproductible](baseline.md), noter les révisions exactes
et conserver une carte connue fonctionnelle comme contrôle.

## Étape 1 — capture simultanée station + monitor

But : savoir si la frame existe encore sur le chemin RX brut après association.

1. Arrêter le gestionnaire réseau et libérer le PHY choisi.
2. Créer `mon0` sur le même PHY AX200.
3. Démarrer une capture complète sur `mon0`.
4. Lancer `frlgtrade.py --live --verbose --phy <phy AX200>`.
5. Marquer précisément l’instant du scan, de l’association et du timeout.
6. Examiner si les vendor-specific Action Frames broadcast continuent après
   l’association.

Commandes de départ à adapter au numéro de PHY réel :

```bash
iw dev
iw phy phy1 info | sed -n '/software interface modes/,/valid interface combinations/p'
pkexec systemctl stop NetworkManager
pkexec iw phy phy1 interface add mon0 type monitor
pkexec ip link set mon0 up
pkexec tcpdump -i mon0 -s 0 -U -w /tmp/ldn-ax200.pcap
```

Dans un second terminal :

```bash
pkexec env PYTHONPATH="$PWD" ./venv/bin/python frlgtrade.py \
  --live --verbose --phy phy1 --monitor-iface mon0 \
  -o output.pk3 PARTY1.pk3 PARTY2.pk3
```

### Attention au nettoyage des interfaces

`frlgsim/transport.py:free_radio()` descend actuellement les interfaces
non-LDN du PHY avant chaque tentative. Le bypass explicite
`--monitor-iface mon0` préserve l’interface indiquée et active le helper ; il
n’est pas actif par défaut et les VIF LDN restent toujours nettoyées. Ne pas
modifier à la main le fichier installé dans `venv`.

Nettoyage après succès comme après exception :

```bash
pkexec ip link set mon0 down
pkexec iw dev mon0 del
pkexec systemctl start NetworkManager
```

Vérifier aussi la disparition de `ldnclient` et `ldn-mon`.

## Critères de validation

### Vérifications offline minimales

Après une modification Python :

```bash
./venv/bin/python -m compileall -q frlgtrade.py frlgsim
./venv/bin/python frlgtrade.py --help >/dev/null
git diff --check
```

### Acceptation hardware

- au moins trois joins AX200 consécutifs ;
- un trade réel terminé et fichier de sortie relu ;
- test avec `power_scheme` par défaut et avec CAM si pertinent ;
- répétition avec une carte connue fonctionnelle ;
- nettoyage correct de `ldnclient`, `ldn-mon`, `mon0` et restauration de
  NetworkManager après succès comme après exception.

Une capture PCAP ou un log contenant des identifiants reste local et hors Git.
