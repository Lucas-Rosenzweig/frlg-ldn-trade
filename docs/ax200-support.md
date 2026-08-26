# Portage Intel AX200 — dossier de reprise agentique

Dernière mise à jour : 2026-08-26
État : diagnostic établi, localisation exacte du filtrage encore à prouver
Dépôt de départ : `tornadus/frlg-ldn-trade`, commit `799b674`

## Objectif et critère de réussite

Faire fonctionner le mode `--live` avec une Intel Wi-Fi 6 AX200 sous Linux sans
régression sur les cartes déjà supportées.

Le succès n'est pas « le scan voit la Switch ». Le test est réussi uniquement
si le programme :

1. détecte et décode l'annonce LDN de la console ;
2. s'associe au réseau ;
3. reçoit l'annonce post-association qui contient son participant ;
4. obtient/configure son adresse `169.254.X.Y` ;
5. termine au moins un échange réel ;
6. répète ce résultat sur plusieurs exécutions, avec un adaptateur connu comme
   contrôle de non-régression.

## Résumé exécutable

La panne reproduite est :

```text
scan monitor -> annonce LDN reçue et décodée
association  -> réussie assez loin pour attendre la mise à jour réseau
post-join    -> aucune annonce exploitable sur le chemin nl80211 de la station
timeout      -> Failed to obtain IP address after joining network (timeout)
```

Ce message n'indique pas un échec DHCP classique. Dans `ldn==0.0.17`,
`Network._initialize_network()` autorise d'abord la station, attend pendant une
seconde une advertisement contenant la MAC locale, puis configure l'adresse IP
extraite de cette advertisement. Le flux provient des Action Frames reçues par
`NL80211_CMD_REGISTER_FRAME`.

L'AX200 utilise `iwlwifi` avec l'op-mode `iwlmvm`. Le PHY testé n'annonce pas
`NL80211_EXT_FEATURE_MULTICAST_REGISTRATIONS`. La bibliothèque `python-netlink`
installée connaît `NL80211_ATTR_RECEIVE_MULTICAST` (valeur 289), mais
`ldn/wlan.py` ne l'ajoute pas à sa requête `REGISTER_FRAME`. Ces deux faits ne
prouvent pas encore à quel étage les trames sont perdues.

**Prochaine action prioritaire :** capturer simultanément les Action Frames sur
une interface monitor `mon0` pendant que `ldnclient` est associé. Ne modifier ni
LDN ni le noyau avant ce test.

## Faits vérifiés

### Dépôt et dépendances

- Branche de départ locale : `main`, alignée sur `origin/main` au commit
  `799b674` lors de la création de ce document.
- `requirements.txt` fixe `ldn==0.0.17`.
- Le code applicatif appelle `ldn.scan()` puis `ldn.connect()` dans
  `frlgsim/transport.py`.
- La dépendance installée enregistre les Action Frames dans
  `ldn/wlan.py:Interface._register_frame()` avec `NL80211_CMD_REGISTER_FRAME`,
  `IFINDEX`, `FRAME_TYPE` et `FRAME_MATCH`, sans `RECEIVE_MULTICAST`.
- La dépendance contient déjà une classe `Monitor` utilisant
  `AF_PACKET/SOCK_RAW` et des trames radiotap. C'est une brique possible pour un
  contournement userspace, pas encore une solution intégrée.
- Le dépôt n'a actuellement aucune suite de tests automatisés versionnée.

### Machine de reproduction communiquée le 2026-08-26

- Distribution : CachyOS (Arch rolling).
- Noyau testé : `7.2.0-1-cachyos`.
- Carte : Intel Wi-Fi 6 AX200, PCI `8086:2723`, sous-système `8086:0084`.
- Pilote : `iwlwifi`; op-mode chargé : `iwlmvm`.
- Firmware chargé : `77.aa2dd297.0 cc-a0-77.ucode`.
- Le mode monitor est annoncé.
- `power_scheme=1` (CAM/actif) a été vérifié et n'a pas changé l'échec.
- Le scan verbose a décodé l'application data et le beacon RFU, puis les trois
  tentatives ont expiré après association avec la même exception.
- La commande de capacité multicast n'a montré que
  `set_multicast_to_unicast`, fonctionnalité différente de l'enregistrement des
  management frames multicast.
- `python-netlink` expose `NL80211_ATTR_RECEIVE_MULTICAST = 289`, mais n'expose
  pas de constante nommée `NL80211_EXT_FEATURE_MULTICAST_REGISTRATIONS` dans la
  version installée.

### API et code noyau amont

- L'UAPI Linux documente que `NL80211_ATTR_RECEIVE_MULTICAST` peut accompagner
  `NL80211_CMD_REGISTER_FRAME` seulement si le PHY annonce
  `NL80211_EXT_FEATURE_MULTICAST_REGISTRATIONS`.
- Le backend Intel `iwlwifi/mld` amont annonce cette extended feature.
- Une recherche du même symbole dans `iwlwifi/mvm/mac80211.c` amont ne retourne
  rien. L'AX200 testée charge `iwlmvm`, pas `iwlwifi/mld`.
- Le README amont classe déjà `Intel AX200 / iwlwifi` comme problématique avec
  « Unable to be assigned ip ».

## Ce qui reste hypothétique

Ne pas transformer les points suivants en faits sans nouvelle capture :

- La trame peut être filtrée dans le firmware AX200 avant d'atteindre le noyau.
- Elle peut atteindre mac80211/iwlmvm mais être exclue du chemin
  `REGISTER_FRAME` de l'interface station.
- Une interface monitor concurrente peut continuer à la recevoir après
  association ; ce test n'a pas encore été exécuté jusqu'au bout.
- Ajouter la feature à `iwlmvm` et l'attribut à LDN peut fonctionner, mais
  annoncer seulement une capability ne crée pas le support firmware nécessaire.
- Un routage hybride « association via station, advertisements via monitor » est
  plausible parce que LDN sait déjà parser les trames monitor, mais il faut
  vérifier coexistence, canal, doublons, cycle de vie et nettoyage des VIF.

## Arbre de décision des correctifs

### Étape 0 — figer un baseline reproductible

Créer une branche de travail et noter les versions exactes. Pour un fork GitHub,
conserver idéalement `upstream` pour `tornadus/frlg-ldn-trade` et utiliser
`origin` pour le fork personnel.

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

### Étape 1 — test décisif station + monitor

But : savoir si la frame existe encore sur le chemin RX brut après association.

1. Arrêter le gestionnaire réseau et libérer le PHY choisi.
2. Créer `mon0` sur le même PHY AX200.
3. Démarrer une capture complète sur `mon0`.
4. Lancer `frlgtrade.py --live --verbose --phy <phy AX200>`.
5. Marquer précisément l'instant du scan, de l'association et du timeout.
6. Examiner si les vendor-specific Action Frames broadcast continuent après
   l'association.

Commandes de départ à adapter au numéro de PHY réel :

```bash
iw dev
iw phy phy1 info | sed -n '/software interface modes/,/valid interface combinations/p'
sudo systemctl stop NetworkManager
sudo iw phy phy1 interface add mon0 type monitor
sudo ip link set mon0 up
sudo tcpdump -i mon0 -s 0 -U -w /tmp/ldn-ax200.pcap
```

Dans un second terminal :

```bash
sudo -E ./venv/bin/python frlgtrade.py \
  --live --verbose --phy phy1 \
  -o output.pk3 PARTY1.pk3 PARTY2.pk3
```

Attention : `frlgsim/transport.py:free_radio()` descend actuellement les
interfaces non-LDN du PHY avant chaque tentative. Pour cette expérience, ajouter
un mécanisme explicite et temporaire permettant de préserver `mon0`; ne pas
modifier à la main le fichier installé dans `venv` et ne pas laisser ce bypass
de diagnostic actif par défaut.

Nettoyage :

```bash
sudo ip link set mon0 down
sudo iw dev mon0 del
sudo systemctl start NetworkManager
```

#### Résultat A — `mon0` voit encore les annonces

Le firmware/chemin RX brut laisse passer les frames. Priorité aux solutions
userspace :

1. reproduire la réception avec un petit probe indépendant ;
2. concevoir une source d'advertisements abstraite dans le fork de LDN ;
3. garder l'association, les clés et les données sur `ldnclient` ;
4. alimenter `_advertisements` depuis la VIF monitor filtrée sur BSSID/canal ;
5. intégrer la dépendance modifiée de façon reproductible ;
6. tester aussi une carte connue fonctionnelle.

Cette voie évite un kernel custom et constitue le meilleur premier correctif si
la capture est positive.

#### Résultat B — `mon0` ne voit plus les annonces

Instrumenter `iwlmvm` avant de changer son comportement :

1. identifier les points RX management/action avant et après filtrage ;
2. ajouter des compteurs/logs ciblés, limités par ratelimit ;
3. compiler les modules correspondant exactement au noyau de test ;
4. charger les modules expérimentaux depuis un boot/kernel de secours ;
5. comparer les compteurs avant/après association.

Si le firmware ne remet jamais la frame au host, un patch Python ou cfg80211 ne
peut pas la recréer. Le projet devient alors un travail de protocole firmware ou
de firmware lui-même, nettement plus risqué.

### Étape 2 — expérience multicast `REGISTER_FRAME`

À tenter seulement si l'instrumentation montre que `iwlmvm` peut réellement
honorer cette sémantique.

- Côté LDN : ajouter conditionnellement l'attribut flag
  `NL80211_ATTR_RECEIVE_MULTICAST` à `_register_frame()`.
- Côté capacité : détecter la feature au runtime et produire un message clair si
  absente ; ne pas envoyer aveuglément l'attribut.
- Côté noyau : n'annoncer
  `NL80211_EXT_FEATURE_MULTICAST_REGISTRATIONS` dans `iwlmvm` qu'avec une
  implémentation vérifiée.
- Test négatif attendu sur le pilote actuel : la requête avec l'attribut devrait
  être refusée comme non supportée. Consigner l'errno et l'extack exacts.

### Étape 3 — firmware ou nouveau driver

Dernier recours seulement. Réécrire un driver AX200 complet dupliquerait le
transport, le chargement firmware et une large surface mac80211 tout en restant
dépendant du protocole du firmware Intel. Un patch firmware/protocole non
documenté est encore plus difficile à distribuer et maintenir. Ne choisir cette
voie qu'après preuve que ni le RX monitor ni un changement `iwlmvm` ne peuvent
exposer la frame.

## Surfaces de modification et coût attendu

| Surface | But | Difficulté | Condition d'entrée |
|---|---|---:|---|
| Fork/intégration Python | dépendance reproductible, détection, logs | facile | toujours |
| Probe station + monitor | localiser la perte | raisonnable | prochaine étape |
| Contournement monitor dans LDN | recevoir les annonces hors station | moyenne | résultat A |
| Instrumentation `iwlmvm` | voir les Action Frames RX | raisonnable | résultat B ou ambigu |
| Patch fonctionnel `iwlmvm` | remonter le multicast correctement | difficile | support démontré |
| Firmware Intel | changer le filtrage embarqué | très difficile | perte prouvée firmware |
| Nouveau driver AX200 | remplacer toute la pile | énorme | non recommandé |

## Journal d'expériences

Ajouter une entrée par test ; ne réécrire pas rétrospectivement les résultats.

| Date | Révisions | Expérience | Observation | Conclusion |
|---|---|---|---|---|
| 2026-08-26 | kernel `7.2.0-1-cachyos`, fw `77.aa2dd297.0`, `ldn 0.0.17` | join AX200 avec `power_scheme=1` | scan/beacon OK, timeout post-association sur 3 essais | power saving non causal ; chemin post-join en échec |
| 2026-08-26 | mêmes versions | inspection `iw phy` et constantes Python | pas de « mgmt frame registration for multicast » ; attribut 289 connu | userspace connaît l'attribut, PHY `iwlmvm` n'annonce pas la feature |

Gabarit :

```text
Date/heure :
Commit application / LDN / kernel :
Matériel + firmware :
Hypothèse testée :
Commande/protocole :
Résultat brut (artefact local, chemin) :
Observation :
Conclusion autorisée :
Prochaine expérience :
Rollback/nettoyage effectué :
```

## Vérifications et garde-fous

Tests offline minimaux après une modification Python :

```bash
./venv/bin/python -m compileall -q frlgtrade.py frlgsim
./venv/bin/python frlgtrade.py --help >/dev/null
git diff --check
```

Tests hardware :

- au moins trois joins AX200 consécutifs ;
- un trade réel terminé et fichier de sortie relu ;
- test avec `power_scheme` par défaut et avec CAM si pertinent ;
- répétition avec une carte connue fonctionnelle ;
- nettoyage correct de `ldnclient`, `ldn-mon`, `mon0` et restauration de
  NetworkManager après succès comme après exception.

Une capture PCAP ou un log contenant des identifiants reste local et hors Git.

## Sources primaires et points de code

- Projet : <https://github.com/tornadus/frlg-ldn-trade>
- LDN : <https://github.com/kinnay/LDN>
- Protocole LDN : <https://github.com/kinnay/NintendoClients/wiki/LDN-Protocol>
- UAPI nl80211 (`REGISTER_FRAME`, `RECEIVE_MULTICAST`) :
  <https://github.com/torvalds/linux/blob/master/include/uapi/linux/nl80211.h>
- Traitement cfg80211 des registrations :
  <https://github.com/torvalds/linux/blob/master/net/wireless/mlme.c>
- Backend Intel MVM utilisé par AX200 :
  <https://github.com/torvalds/linux/tree/master/drivers/net/wireless/intel/iwlwifi/mvm>
- Backend Intel MLD qui annonce actuellement la feature multicast :
  <https://github.com/torvalds/linux/blob/master/drivers/net/wireless/intel/iwlwifi/mld/mac80211.c>
- Instructions agentiques Codex :
  <https://learn.chatgpt.com/docs/agent-configuration/agents-md>

Les liens `master` décrivent l'amont courant, pas forcément le noyau CachyOS
installé. Pour toute implémentation, figer aussi le tag/commit correspondant au
noyau réellement compilé.
