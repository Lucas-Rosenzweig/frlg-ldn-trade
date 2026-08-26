# Journal d’expériences

[← Retour à l’index du dossier](index.md)

Ajouter une entrée par test ; ne pas réécrire rétrospectivement les résultats.
Les artefacts sensibles restent locaux et sont seulement référencés de façon
redacted dans ce journal.

| Date | Révisions | Expérience | Observation | Conclusion |
|---|---|---|---|---|
| 2026-08-26 | kernel `7.2.0-1-cachyos`, fw `77.aa2dd297.0`, `ldn 0.0.17` | join AX200 avec `power_scheme=1` | scan/beacon OK, timeout post-association sur 3 essais | power saving non causal ; chemin post-join en échec |
| 2026-08-26 | mêmes versions | inspection `iw phy` et constantes Python | pas de « mgmt frame registration for multicast » ; attribut 289 connu | userspace connaît l’attribut, PHY `iwlmvm` n’annonce pas la feature |
| 2026-08-26 | app `4b4ce60` + bypass local, kernel `7.2.0-1-cachyos`, fw `77.aa2dd297.0`, `ldn 0.0.17` | `mon0` + `ldnclient` sur `phy1`, capture bornée au join | 3 timeouts « Failed to obtain IP address » ; 53 Action Frames vendor-specific sur 8,7 s, 0 perte noyau | résultat A : le RX brut monitor continue après association ; priorité au contournement userspace, sans conclusion sur l’étage exact du filtrage station |
| 2026-08-26 | app `4b4ce60` + outils locaux, kernel `7.2.0-1-cachyos`, fw `77.aa2dd297.0`, `ldn 0.0.17` | probe LDN sur `mon0` pendant `ldnclient` | 3 mêmes timeouts post-association ; 41 advertisements LDN décodés en 15 s | résultat A confirmé sans `tcpdump` ; le décodeur LDN peut alimenter une source monitor userspace |
| 2026-08-26 | app `4b4ce60` + fork local `ldn 0.0.17`, kernel `7.2.0-1-cachyos`, fw `77.aa2dd297.0` | join minimal sans trade, `--monitor-iface mon0`, jusqu’à 3 tentatives | au moins une tentative atteint l’initialisation réseau ; arrêt propre immédiat ; des tentatives précédentes ont encore expiré | le contournement monitor est viable pour l’IP ; ne pas revendiquer le succès live complet avant un trade et un contrôle non-régression |
| 2026-08-26 | mêmes révisions, fork monitor | join minimal puis flux live, monitor lié après puis avant association | échecs toujours présents ; après liaison pré-association, RX monitor observé mais aucune advertisement décodée dans la fenêtre | comportement intermittent ; instrumenter séparément Action / vendor-specific / source avant tout assouplissement du filtre |

## Gabarit d’entrée

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
