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
| 2026-08-26 | mêmes révisions, fork monitor instrumenté | join minimal sur session Switch relancée, avec puis sans membership promiscuous AF_PACKET | 18–21 trames RX ; 1 Action Frame ; 0 vendor-specific et 0 advertisement décodée dans les deux cas ; timeout | le socket Python ne reçoit pas le même sous-ensemble post-association que `tcpdump` ; membership promiscuous seul non causal |
| 2026-08-27 | mêmes révisions, probe avec comptage temporel | probe monitor + join minimal sur session Switch en attente | 4 advertisements décodés, regroupés dans une seule seconde ; join : 19 RX, 1 Action, 0 vendor-specific, timeout | temporisation entre deux commandes non fiable comme marqueur de phase ; prochain test avec marqueur explicite |
| 2026-08-27 | mêmes révisions, probe et fork `Scanner` | probe externe marqué à t=3 puis join minimal ; lecteur intégré instrumenté | probe externe : advertisements continus après t=6 ; lecteur intégré : 19 RX, 0 Action, 0 vendor-specific, timeout | la coexistence dans le processus LDN modifie le sous-ensemble reçu ; essayer un helper monitor séparé avec IPC, sans assouplir le filtre ni toucher au noyau |
| 2026-08-27 | helper monitor IPC, fork externe | join minimal sur session Switch relancée | helper prêt sans erreur IPC ; timeout post-association | instrumenter le nombre d’advertisements remis au fork avant de conclure sur le filtrage LDN |
| 2026-08-27 | helper IPC lancé avant scan, fork source externe | joins minimaux sur même session hôte | scan fiable avec dwell 1 s ; 10–11 advertisements IPC, tous revalidés ; aucune annonce ne contient le participant local, y compris après 10 s | le helper et la revalidation fonctionnent ; il faut localiser pourquoi le flux post-autorisation cesse côté helper avant de prétendre corriger AX200 |

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
