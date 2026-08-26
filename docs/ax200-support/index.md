# Portage Intel AX200 — dossier de reprise agentique

- Dernière mise à jour : 2026-08-27
- État : le helper monitor IPC reçoit et fait revalider des advertisements ; le
  join AX200 n’obtient toutefois pas encore d’adresse IP et la Switch reste en
  attente. Aucun trade ni contrôle de non-régression n’est validé.
- Dépôt de départ : `tornadus/frlg-ldn-trade`, commit `799b674`

Ce dossier est l’entrée unique de l’enquête AX200. Les faits, la procédure, les
expériences, les décisions et les sources vivent dans des pages séparées afin
de garder l’état courant court et le journal historique append-only.

## Navigation

- [État technique, faits vérifiés et hypothèses](findings.md)
- [Baseline reproductible et environnement](baseline.md)
- [Procédure hardware, validation et nettoyage](procedure.md)
- [Arbre de décision et surfaces de correction](decisions.md)
- [Journal d’expériences](experiments.md)
- [Sources primaires et points de code](references.md)

## Objectif et critère de réussite

Faire fonctionner le mode `--live` avec une Intel Wi-Fi 6 AX200 sous Linux sans
régression sur les cartes déjà supportées.

Le succès n’est pas « le scan voit la Switch ». Le test est réussi uniquement
si le programme :

1. détecte et décode l’annonce LDN de la console ;
2. s’associe au réseau ;
3. reçoit l’annonce post-association qui contient son participant ;
4. obtient/configure son adresse `169.254.X.Y` ;
5. termine au moins un échange réel ;
6. répète ce résultat sur plusieurs exécutions, avec un adaptateur connu comme
   contrôle de non-régression.

## État en une minute

La panne reproduite suit ce chemin :

```text
scan monitor -> annonce LDN reçue et décodée
association  -> réussie assez loin pour attendre la mise à jour réseau
post-join    -> aucune annonce exploitable sur le chemin nl80211 de la station
timeout      -> Failed to obtain IP address after joining network (timeout)
```

Dans `ldn==0.0.17`, l’initialisation réseau attend une advertisement contenant
la MAC locale avant de configurer l’adresse IP. Le chemin attendu passe par les
Action Frames enregistrées avec `NL80211_CMD_REGISTER_FRAME`.

Le test station + monitor du 2026-08-26 a toutefois reçu 53 Action Frames
vendor-specific sur `mon0` pendant 8,7 secondes, puis le probe LDN a décodé 41
advertisements en 15 secondes. Le helper séparé, lancé avant le scan, a remis
10–11 advertisements par tentative au fork LDN, toutes revalidées. Aucune ne
contenait toutefois le participant local, y compris après 10 secondes :
l’initialisation réseau ne démarre donc pas.

**Prochaine action prioritaire :** instrumenter le helper et la phase LDN pour
déterminer pourquoi les advertisements post-autorisation cessent d’être reçues
ou ne contiennent pas le participant local. N’exécuter un trade réel et le
contrôle sur une carte connue fonctionnelle qu’après l’obtention répétée de
l’adresse IP. Ne modifier ni le noyau ni son annonce de capability avant ces
validations.

Le probe versionné et le protocole exact sont décrits dans la
[procédure hardware](procedure.md). Les révisions et précautions de baseline
sont dans [baseline.md](baseline.md).

## Convention de reprise

Les pages distinguent explicitement les observations, les hypothèses et les
conclusions autorisées. Une nouvelle expérience est ajoutée au
[journal](experiments.md) avec ses révisions, sa commande, son résultat brut,
sa conclusion et son nettoyage ; elle ne réécrit pas les résultats précédents.

Cette organisation s’inspire des recommandations de l’[OpenAI Docs —
AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md) :
contexte et attentes explicites, règles concises, et découpage des fichiers
volumineux en sous-fichiers lorsque cela protège les informations importantes.
