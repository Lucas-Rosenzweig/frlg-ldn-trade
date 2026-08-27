# Premier échange AX200 réussi — 2026-08-27

[← Retour à l’index du dossier](index.md)

Cette page est le compte rendu reproductible du premier échange complet entre
une Intel AX200 Linux et une vraie Switch. Elle complète le journal append-only
avec la chronologie, les conditions de succès, les limites et le nettoyage.

## Portée du résultat

Le résultat établi est un succès fonctionnel unique du contournement
userspace. Il ne prouve pas que la réception des Action Frames sur l’interface
station est réparée : aucune advertisement post-autorisation contenant le
participant local n’a été reçue. Après un délai de 10 secondes, le fork LDN a
utilisé son inférence d’adresse strictement gardée et a configuré
`169.254.X.2`.

Le test a ensuite terminé toutes les couches :

```text
scan monitor 1/6/11
  -> scan géré ciblé sur le canal trouvé
  -> NL80211 CONNECT + événement d’association
  -> authentification et autorisation LDN
  -> délai sans annonce post-autorisation
  -> inférence gardée 169.254.X.2
  -> Net + Session PIA (type 5, ack type 6)
  -> RTT/Reliable
  -> RFU A + JOIN_GROUP_OK
  -> LinkPlayer + cartes + équipes
  -> sélection et échange Pokémon
  -> écriture output.pk3
  -> BOTH_CANCEL_TRADE
  -> EXIT_ROOM + READY_CLOSE_LINK + D
```

## Baseline exact

- Date : 2026-08-27, fuseau Europe/Paris.
- Application de base : `3c46554`, avec worktree local non commité.
- Noyau : `7.2.0-1-cachyos`.
- Carte : Intel Wi-Fi 6 AX200, pilote `iwlwifi`, op-mode `iwlmvm`.
- Firmware : `77.aa2dd297.0 cc-a0-77.ucode`.
- Python : environnement virtuel du dépôt.
- Dépendances : `ldn 0.0.17` via `vendor/ldn`,
  `python-netlink 0.0.15`, `trio 0.33.0`.
- PHY/interface : `phy0`, `wlan0`, VIF monitor temporaire `mon0`.
- Canal de la session réussie : 11.

Les SSID, MAC, noms, identifiants, clés, parties et logs complets restent
locaux et ne doivent jamais être copiés dans Git.

## Précondition essentielle : un seul client

Les commandes live lancées par `pkexec` créent un enfant root. Envoyer Ctrl-C
au shell appelant n’a pas toujours arrêté cet enfant pendant l’enquête. Plusieurs
clients live et helpers sont ainsi restés actifs simultanément et le même salon
renvoyait continuellement une réponse Session avec `field3=8`, sans type 5.

Avant le test réussi, tous les enfants privilégiés ont été tués, `ldnclient` a
été supprimée, puis le salon meneur a été recréé. Sur le salon neuf, un unique
client a immédiatement reçu la mise à jour Session type 5 ; la réponse compacte
avait `field3=1`. La signification normative de ce champ n’est pas documentée :
ces valeurs sont des observations, pas des noms d’erreur.

Contrôle préalable :

```bash
pgrep -af 'frlgtrade.py --live|frlgsim.monitor_helper'
pkexec pkill -f '/chemin/absolu/frlgtrade.py --live'
pkexec pkill -f 'frlgsim.monitor_helper'
pkexec ip link set ldnclient down 2>/dev/null || true
pkexec iw dev ldnclient del 2>/dev/null || true
```

Après ce nettoyage, quitter et recréer le salon meneur côté Switch avant la
nouvelle tentative.

## Commande et préparation reproduites

Depuis la racine du dépôt, avec les chemins adaptés :

```bash
pkexec systemctl stop NetworkManager
pkexec iw phy phy0 interface add mon0 type monitor
pkexec ip link set mon0 up

pkexec env PYTHONUNBUFFERED=1 PYTHONPATH="$PWD" \
  "$PWD/venv/bin/python" "$PWD/frlgtrade.py" \
  --live --verbose --phy phy0 --monitor-iface mon0 --ot EMU \
  --keys /chemin/absolu/vers/prod.keys \
  -o "$PWD/output.pk3" \
  "$PWD/PARTY1.pk3" "$PWD/PARTY2.pk3"
```

Le helper balaie 1/6/11 pour la découverte. Une fois le réseau trouvé, le fork
fait un scan géré ciblé avec `iw dev ldnclient scan freq <fréquence>` avant
`NL80211_CMD_CONNECT`, puis remet l’interface UP. Ces deux opérations sont
distinctes : le helper découvre l’annonce LDN, tandis que le scan géré peuple
le cache BSS nécessaire à l’association AX200.

## Jalons observés

Les temps sont indicatifs et relatifs au lancement :

| Temps | Jalon |
|---:|---|
| 3,5 s | réseau LDN détecté sur le canal 11 |
| 3,7 s | événement CONNECT, station créée, authentification terminée |
| 13,7 s | `address-inferred`, socket UDP prête |
| 14,1 s | Session type 5 reçue, ack type 6 mis en file |
| 14,2 s | RTT reçu, connexion PIA établie |
| 15,5 s | acceptation RFU `A` |
| 20,1 s | `JOIN_GROUP_OK` |
| 23,7 s | échange LinkPlayer terminé |
| 75,5 s | menu d’échange prêt |
| 92,6 s | sélection des deux Pokémon validée |
| 135,2 s | échange commité et `.pk3` écrit, checksum valide |
| 191,5 s | annulation post-échange acquittée |
| 205,7 s | fermeture RFU `D` reçue |

Le fichier reçu faisait 100 octets et son checksum Pokémon était valide. Son
contenu nominatif n’est pas nécessaire à la preuve et ne doit pas être ajouté
aux fixtures ou à la documentation versionnée.

## Changements techniques impliqués

- `frlgsim/monitor_helper.py` : helper hors processus, IPC Unix privé,
  télémétrie agrégée et marqueurs de phase.
- `frlgsim/transport.py` : résolution du chemin de clés sous `pkexec`, balayage
  monitor 1/6/11, cycle de vie du helper, délais/cancellation, activation du
  scan préalable et de l’inférence seulement avec `--monitor-iface`.
- `vendor/ldn/ldn/wlan.py` : scan géré ciblé avant CONNECT et jalons nl80211.
- `vendor/ldn/ldn/__init__.py` : source d’advertisements externe, compteurs de
  phase et inférence d’adresse bornée.
- `frlgsim/pia_connect.py` : acceptation pilotée par le type 5 et ack type 6 ;
  le type 2 compact ne suffit pas à déclarer la connexion établie.
- `frlgtrade.py` : variable id PIA fraîche en live, partagée entre la couche
  Session et le simulateur.

Le chemin des adaptateurs historiques reste inchangé par défaut : scan LDN
normal, aucune source monitor, aucun scan préalable forcé et aucune inférence
d’adresse.

## Limites et prochaine validation

La correction ne peut pas encore être déclarée définitive :

1. répéter deux fois sur AX200, chaque fois avec un salon neuf et zéro enfant
   live résiduel ;
2. répéter avec un adaptateur listé comme fonctionnel dans le README ;
3. confirmer que le chemin sans `--monitor-iface` n’active ni scan préalable
   AX200 ni inférence ;
4. conserver comme défaut ouvert l’absence des advertisements
   post-autorisation sur AX200.

## Nettoyage validé

Après la fermeture du jeu :

```bash
pkexec pkill -f '/chemin/absolu/frlgtrade.py --live' 2>/dev/null || true
pkexec pkill -f 'frlgsim.monitor_helper' 2>/dev/null || true
pkexec ip link set ldnclient down 2>/dev/null || true
pkexec iw dev ldnclient del 2>/dev/null || true
pkexec ip link set mon0 down 2>/dev/null || true
pkexec iw dev mon0 del 2>/dev/null || true
pkexec systemctl start NetworkManager
```

Vérifier ensuite que NetworkManager est actif, que seule l’interface gérée
normale subsiste et qu’aucun processus live/helper n’est présent.
