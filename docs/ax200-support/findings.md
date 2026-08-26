# Faits vérifiés et hypothèses

[← Retour à l’index du dossier](index.md)

Cette page sépare les observations établies des hypothèses encore à tester.
Une capture positive sur le chemin monitor ne localise pas à elle seule
l’étage exact du filtrage dans l’interface station.

## Modèle de panne reproduite

```text
scan monitor -> annonce LDN reçue et décodée
association  -> réussie assez loin pour attendre la mise à jour réseau
post-join    -> aucune annonce exploitable sur le chemin nl80211 de la station
timeout      -> Failed to obtain IP address after joining network (timeout)
```

Ce message n’indique pas un échec DHCP classique. Dans `ldn==0.0.17`,
`Network._initialize_network()` autorise d’abord la station, attend pendant une
seconde une advertisement contenant la MAC locale, puis configure l’adresse IP
extraite de cette advertisement. Le flux provient des Action Frames reçues par
`NL80211_CMD_REGISTER_FRAME`.

L’AX200 utilise `iwlwifi` avec l’op-mode `iwlmvm`. Le PHY testé n’annonce pas
`NL80211_EXT_FEATURE_MULTICAST_REGISTRATIONS`. La bibliothèque
`python-netlink` installée connaît `NL80211_ATTR_RECEIVE_MULTICAST` (valeur
289), mais `ldn/wlan.py` ne l’ajoute pas à sa requête `REGISTER_FRAME`. Ces
deux faits ne prouvent pas encore à quel étage les trames sont perdues.

## Faits vérifiés

### Dépôt et dépendances

- Branche de départ locale : `main`, alignée sur `origin/main` au commit
  `799b674` lors de la création du dossier.
- Le runtime cible reste `ldn==0.0.17` ; `requirements.txt` pointe désormais
  vers le fork local reproductible `vendor/ldn`.
- Le code applicatif appelle `ldn.scan()` puis `ldn.connect()` dans
  `frlgsim/transport.py`.
- La dépendance installée enregistre les Action Frames dans
  `ldn/wlan.py:Interface._register_frame()` avec `NL80211_CMD_REGISTER_FRAME`,
  `IFINDEX`, `FRAME_TYPE` et `FRAME_MATCH`, sans `RECEIVE_MULTICAST`.
- La dépendance contient déjà une classe `Monitor` utilisant
  `AF_PACKET/SOCK_RAW` et des trames radiotap. C’est une brique possible pour
  un contournement userspace, pas encore une solution intégrée.
- Le dépôt n’a actuellement aucune suite de tests automatisés versionnée.

### Résultats monitor et fork userspace

- Le test simultané station + monitor du 2026-08-26 a reproduit trois timeouts
  post-association pendant qu’une capture `mon0`, bornée au join, recevait 53
  Action Frames vendor-specific sur 8,7 s, sans perte noyau. Le chemin RX brut
  reste donc alimenté après association.
- Le probe userspace versionné a décodé 41 advertisements LDN sur `mon0` dans
  une fenêtre de 15 s pendant les mêmes trois timeouts post-association. Le
  contournement monitor peut donc réutiliser le décodeur LDN ; ce résultat ne
  dépend pas de `tcpdump`.
- Le fork local `vendor/ldn` ajoute `ConnectNetworkParam.ifname_monitor` : il
  alimente la file d’advertisements de la station depuis une VIF monitor déjà
  existante, sans créer ni supprimer cette VIF. Le join minimal AX200 a atteint
  l’initialisation réseau au moins une fois avec ce chemin ; le trade complet
  n’a pas encore été exécuté.
- Les essais avec le fork monitor restent intermittents : après liaison
  pré-association, le RX monitor a été observé mais aucune advertisement n’a
  été décodée dans une fenêtre ; les échecs persistent.

### Machine de reproduction communiquée le 2026-08-26

- Distribution : CachyOS (Arch rolling).
- Noyau testé : `7.2.0-1-cachyos`.
- Carte : Intel Wi-Fi 6 AX200, PCI `8086:2723`, sous-système `8086:0084`.
- Pilote : `iwlwifi` ; op-mode chargé : `iwlmvm`.
- Firmware chargé : `77.aa2dd297.0 cc-a0-77.ucode`.
- Le mode monitor est annoncé.
- `power_scheme=1` (CAM/actif) a été vérifié et n’a pas changé l’échec.
- Le scan verbose a décodé l’application data et le beacon RFU, puis les trois
  tentatives ont expiré après association avec la même exception.
- La commande de capacité multicast n’a montré que
  `set_multicast_to_unicast`, fonctionnalité différente de l’enregistrement
  des management frames multicast.
- `python-netlink` expose `NL80211_ATTR_RECEIVE_MULTICAST = 289`, mais
  n’expose pas de constante nommée
  `NL80211_EXT_FEATURE_MULTICAST_REGISTRATIONS` dans la version installée.

### API et code noyau amont

- L’UAPI Linux documente que `NL80211_ATTR_RECEIVE_MULTICAST` peut accompagner
  `NL80211_CMD_REGISTER_FRAME` seulement si le PHY annonce
  `NL80211_EXT_FEATURE_MULTICAST_REGISTRATIONS`.
- Le backend Intel `iwlwifi/mld` amont annonce cette extended feature.
- Une recherche du même symbole dans `iwlwifi/mvm/mac80211.c` amont ne retourne
  rien. L’AX200 testée charge `iwlmvm`, pas `iwlwifi/mld`.
- Le README amont classe déjà `Intel AX200 / iwlwifi` comme problématique avec
  « Unable to be assigned ip ».

## Ce qui reste hypothétique

Ne pas transformer les points suivants en faits sans nouvelle capture :

- La trame peut être filtrée dans le firmware AX200 avant d’atteindre le
  noyau.
- Elle peut atteindre mac80211/iwlmvm mais être exclue du chemin
  `REGISTER_FRAME` de l’interface station.
- Ajouter la feature à `iwlmvm` et l’attribut à LDN peut fonctionner, mais
  annoncer seulement une capability ne crée pas le support firmware nécessaire.
- Un routage hybride « association via station, advertisements via monitor »
  est plausible parce que LDN sait déjà parser les trames monitor, mais il faut
  vérifier coexistence, canal, doublons, cycle de vie et nettoyage des VIF.

## Conclusion autorisée à ce stade

Le chemin RX brut monitor est alimenté après association et le décodeur LDN
peut traiter des advertisements sur ce chemin. Cela justifie de valider le
contournement userspace avant toute modification noyau ou toute annonce de
capability. Cela ne constitue pas encore une correction live complète.
