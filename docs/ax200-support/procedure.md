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
  --live --verbose --phy phy0 --monitor-iface mon0 \
  --keys /chemin/absolu/vers/prod.keys \
  -o output.pk3 PARTY1.pk3 PARTY2.pk3
```

Le helper doit être prêt avant le scan. Sur l’AX200 testée, le chemin live fait
aussi un scan géré ciblé avant CONNECT. Si aucune annonce post-autorisation ne
contient le participant local après 10 secondes, le fork peut inférer
`169.254.X.2` uniquement lorsque l’annonce initiale décrit exactement un hôte
`169.254.X.1`, un seul participant et une capacité d’au moins deux joueurs.
Cette inférence a permis un échange complet, mais reste un contournement à
répéter et non une preuve de réparation du RX Action Frame.

Le chemin `--monitor-iface` effectue les opérations suivantes :

1. démarrage du helper hors processus et de son socket Unix privée ;
2. balayage explicite des canaux LDN 1, 6 et 11 ;
3. création de `ldnclient` ;
4. scan géré ciblé sur la fréquence trouvée afin de peupler le cache BSS ;
5. CONNECT, authentification et autorisation ;
6. attente de l’annonce contenant la MAC locale ;
7. après 10 s seulement, inférence éventuelle de `.2` sous garde stricte ;
8. démarrage PIA/RFU puis échange.

Le chemin normal sans `--monitor-iface` n’active ni le helper, ni le scan géré
préalable, ni l’inférence. Cette séparation protège les adaptateurs déjà
supportés.

## Procédure du test live AX200 réussi

### 1. Garantir l’absence d’un ancien client

```bash
pgrep -af 'frlgtrade.py --live|frlgsim.monitor_helper'
pkexec pkill -f '/chemin/absolu/frlgtrade.py --live' 2>/dev/null || true
pkexec pkill -f 'frlgsim.monitor_helper' 2>/dev/null || true
pkexec ip link set ldnclient down 2>/dev/null || true
pkexec iw dev ldnclient del 2>/dev/null || true
```

Ne pas considérer Ctrl-C sur le shell appelant comme une preuve que l’enfant
`pkexec` est arrêté. Vérifier à nouveau avec `pgrep`.

### 2. Préparer la radio

```bash
pkexec systemctl stop NetworkManager
pkexec iw phy phy0 interface add mon0 type monitor
pkexec ip link set mon0 up
```

Créer ensuite un salon meneur neuf sur la Switch et rester sur « Attente d’un
autre joueur ». Un salon ayant reçu plusieurs clients concurrents doit être
quitté puis recréé.

### 3. Lancer un unique client

```bash
pkexec env PYTHONUNBUFFERED=1 PYTHONPATH="$PWD" \
  "$PWD/venv/bin/python" "$PWD/frlgtrade.py" \
  --live --verbose --phy phy0 --monitor-iface mon0 --ot EMU \
  --keys /chemin/absolu/vers/prod.keys \
  -o "$PWD/output.pk3" \
  "$PWD/PARTY1.pk3" "$PWD/PARTY2.pk3"
```

Les jalons minimaux attendus sont : `connect-event`, `station-created`,
`authentication-complete`, `authorized`, puis `address-configured` ou
`address-inferred`. Ensuite doivent apparaître Session type 5, RTT/Reliable,
`JOIN_GROUP_OK`, l’acceptation RFU `A` et l’échange LinkPlayer.

### 4. Actions côté Switch

Une fois le menu d’échange ouvert : sélectionner le Pokémon, confirmer
l’échange, laisser l’animation et la sauvegarde se terminer, puis attendre
l’annulation automatique du client. Après le retour dans la salle, marcher
vers la sortie sud et confirmer afin que le host envoie `EXIT_ROOM`,
`READY_CLOSE_LINK` puis `D`.

### 5. Vérifier le résultat

Le log doit annoncer `CONFIRM_FINISH_TRADE`, un checksum valide et l’écriture
du fichier de sortie. Un `.pk3` de partie Gen 3 fait 100 octets dans ce chemin.
La preuve complète attend aussi `BOTH_CANCEL_TRADE` et la fermeture RFU `D`.

Voir [le compte rendu du premier succès](first-success.md) pour la chronologie
mesurée.

Lors d'un timeout, relever le suffixe agrégé de l'erreur, sans conserver le log
verbeux : `after-authorize=...` sépare les advertisements reçues/acceptées après
l'autorisation ; `local-participant=...` indique celles qui portent la MAC
locale ; les compteurs `helper phase/raw/radiotap/action/vendor/decoded`
localisent la perte dans le helper. Ces compteurs ne contiennent ni MAC, ni
SSID, ni payload. Une phase autre que `authorized` signifie que le marqueur
local n'a pas encore été traité par le helper, donc le résultat est ambigu.

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
  --keys /chemin/absolu/vers/prod.keys \
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

Vérifications finales :

```bash
systemctl is-active NetworkManager
iw dev
pgrep -af 'frlgtrade.py --live|frlgsim.monitor_helper'
```

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
- un trade réel terminé et fichier de sortie relu — acquis une fois le
  2026-08-27 ;
- test avec `power_scheme` par défaut et avec CAM si pertinent ;
- répétition avec une carte connue fonctionnelle ;
- nettoyage correct de `ldnclient`, `ldn-mon`, `mon0` et restauration de
  NetworkManager après succès comme après exception.

Une capture PCAP ou un log contenant des identifiants reste local et hors Git.
