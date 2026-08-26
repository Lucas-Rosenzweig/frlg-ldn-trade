# Sources primaires et points de code

[← Retour à l’index du dossier](index.md)

## Projet et protocole

- Projet : <https://github.com/tornadus/frlg-ldn-trade>
- LDN : <https://github.com/kinnay/LDN>
- Protocole LDN : <https://github.com/kinnay/NintendoClients/wiki/LDN-Protocol>

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
