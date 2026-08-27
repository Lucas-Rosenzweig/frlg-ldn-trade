# Sources primaires et points de code

[← Retour à l’index du dossier](index.md)

## Projet et protocole

- Projet : <https://github.com/tornadus/frlg-ldn-trade>
- LDN : <https://github.com/kinnay/LDN>
- Protocole LDN : <https://github.com/kinnay/NintendoClients/wiki/LDN-Protocol>
- Vue d’ensemble PIA et séquence de join :
  <https://github.com/kinnay/NintendoClients/wiki/Pia-Overview>
- Protocole PIA et en-têtes :
  <https://github.com/kinnay/NintendoClients/wiki/Pia-Protocol>
- Session Protocol 6.x, types 0/2/5/6 :
  <https://github.com/kinnay/NintendoClients/wiki/Session-Protocol-(new)>
- Types PIA, notamment variable id par session :
  <https://github.com/kinnay/NintendoClients/wiki/Pia-Types>

## Linux et Intel

- UAPI nl80211 (`REGISTER_FRAME`, `RECEIVE_MULTICAST`) :
  <https://github.com/torvalds/linux/blob/master/include/uapi/linux/nl80211.h>
- Traitement cfg80211 des registrations :
  <https://github.com/torvalds/linux/blob/master/net/wireless/mlme.c>
- Backend Intel MVM utilisé par AX200 :
  <https://github.com/torvalds/linux/tree/master/drivers/net/wireless/intel/iwlwifi/mvm>
- Backend Intel MLD qui annonce actuellement la feature multicast :
  <https://github.com/torvalds/linux/blob/master/drivers/net/wireless/intel/iwlwifi/mld/mac80211.c>

## Documentation agentique

- Instructions agentiques Codex :
  <https://learn.chatgpt.com/docs/agent-configuration/agents-md>

Les liens `master` décrivent l’amont courant, pas forcément le noyau CachyOS
installé. Pour toute implémentation, figer aussi le tag ou commit correspondant
au noyau réellement compilé.

## Points de code du contournement validé une fois

- `frlgsim/monitor_helper.py` : capture monitor et IPC.
- `frlgsim/transport.py` : balayage 1/6/11, cycle de vie du helper, activation
  monitor-only du scan préalable et de l’inférence.
- `vendor/ldn/ldn/wlan.py` : scan BSS géré avant CONNECT.
- `vendor/ldn/ldn/__init__.py` : attente post-autorisation et garde d’inférence.
- `frlgsim/pia_connect.py` : Session type 5 / ack type 6 et jalons PIA.
- `frlgtrade.py` : variable id live fraîche et lancement du simulateur.

Le détail et la chronologie sont dans [first-success.md](first-success.md).
