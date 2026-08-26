# Arbre de décision et surfaces de correction

[← Retour à l’index du dossier](index.md)

La cause racine reste non prouvée tant qu’une capture simultanée managed +
monitor n’a pas établi où les broadcast Action Frames cessent. Le résultat A
déjà observé autorise toutefois l’exploration userspace en priorité.

## Étape 1 — interpréter la capture station + monitor

### Résultat A — `mon0` voit encore les annonces

Le firmware/chemin RX brut laisse passer les frames. Priorité aux solutions
userspace :

1. reproduire la réception avec un petit probe indépendant ;
2. concevoir une source d’advertisements abstraite dans le fork de LDN ;
3. garder l’association, les clés et les données sur `ldnclient` ;
4. alimenter `_advertisements` depuis la VIF monitor filtrée sur BSSID/canal ;
5. intégrer la dépendance modifiée de façon reproductible ;
6. tester aussi une carte connue fonctionnelle.

Cette voie évite un kernel custom et constitue le meilleur premier correctif si
la capture est positive.

### État de cette voie au 2026-08-27

Les étapes 1 à 5 ont été réalisées sous la forme d’un helper monitor séparé et
d’un IPC Unix strict. Le helper est lancé avant le scan et ses advertisements
sont revalidées par le fork LDN. Il reçoit actuellement seulement des annonces
pré-autorisation : elles ne contiennent pas la MAC du participant local et ne
permettent donc pas de configurer l’adresse IP. La prochaine expérience reste
dans cette branche : instrumenter précisément la phase de l’annonce et l’état
du helper, sans assouplir les validations ni toucher au noyau.

### Résultat B — `mon0` ne voit plus les annonces

Instrumenter `iwlmvm` avant de changer son comportement :

1. identifier les points RX management/action avant et après filtrage ;
2. ajouter des compteurs/logs ciblés, limités par ratelimit ;
3. compiler les modules correspondant exactement au noyau de test ;
4. charger les modules expérimentaux depuis un boot/kernel de secours ;
5. comparer les compteurs avant/après association.

Si le firmware ne remet jamais la frame au host, un patch Python ou cfg80211 ne
peut pas la recréer. Le projet devient alors un travail de protocole firmware ou
de firmware lui-même, nettement plus risqué.

## Étape 2 — expérience multicast `REGISTER_FRAME`

À tenter seulement si l’instrumentation montre que `iwlmvm` peut réellement
honorer cette sémantique.

- Côté LDN : ajouter conditionnellement l’attribut flag
  `NL80211_ATTR_RECEIVE_MULTICAST` à `_register_frame()`.
- Côté capacité : détecter la feature au runtime et produire un message clair
  si absente ; ne pas envoyer aveuglément l’attribut.
- Côté noyau : n’annoncer
  `NL80211_EXT_FEATURE_MULTICAST_REGISTRATIONS` dans `iwlmvm` qu’avec une
  implémentation vérifiée.
- Test négatif attendu sur le pilote actuel : la requête avec l’attribut devrait
  être refusée comme non supportée. Consigner l’errno et l’extack exacts.

## Étape 3 — firmware ou nouveau driver

Dernier recours seulement. Réécrire un driver AX200 complet dupliquerait le
transport, le chargement firmware et une large surface mac80211 tout en restant
dépendant du protocole du firmware Intel. Un patch firmware/protocole non
documenté est encore plus difficile à distribuer et maintenir. Ne choisir cette
voie qu’après preuve que ni le RX monitor ni un changement `iwlmvm` ne peuvent
exposer la frame.

## Surfaces de modification et coût attendu

| Surface | But | Difficulté | Condition d’entrée |
|---|---|---:|---|
| Fork/intégration Python | dépendance reproductible, détection, logs | facile | toujours |
| Probe station + monitor | localiser la perte | raisonnable | prochaine étape |
| Contournement monitor dans LDN | recevoir les annonces hors station | moyenne | résultat A |
| Instrumentation `iwlmvm` | voir les Action Frames RX | raisonnable | résultat B ou ambigu |
| Patch fonctionnel `iwlmvm` | remonter le multicast correctement | difficile | support démontré |
| Firmware Intel | changer le filtrage embarqué | très difficile | perte prouvée firmware |
| Nouveau driver AX200 | remplacer toute la pile | énorme | non recommandé |
