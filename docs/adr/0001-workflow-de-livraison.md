# ADR 0001 — Workflow de livraison obligatoire

**Statut :** Accepté
**Date :** 2026-11-18

## Contexte

L'agent tourne sur ~29 bornes photobooth installées dans des bars. Une
régression n'est pas rattrapable à chaud : la borne est sur site, elle encaisse
des paiements, et une panne se traduit directement en chiffre d'affaires perdu
et en clients qui paient sans recevoir leur photo.

Plusieurs incidents récents ont été causés par du code déployé trop vite, sans
relecture indépendante :

- **v1.0.28.14** — le nettoyage des dossiers `_MEI` supprimait celui de l'agent
  en cours d'exécution. PyInstaller y stocke `certifi/cacert.pem`, donc tout
  HTTPS cassait : plus de heartbeat, PIN admin refusé, transactions jamais
  marquées, aucune alerte SMS. Le bug a mis **sept semaines** à être identifié
  (25/09 → 13/11) et a laissé 1704 transactions non surveillées.
- **v1.0.28.22** — le pool HTTP partagé a été introduit sans verrou alors que
  l'agent a quatre threads qui tapent Supabase en parallèle. Le défaut n'a été
  vu que parce qu'un relecteur indépendant a été sollicité après coup.
- **v1.0.28.9** — appel de `Cx2Stat64.dll` sur une imprimante non supportée,
  segfault natif qui tuait le process entier (MB-50).

Le point commun : chacun de ces défauts était visible à la relecture, mais
invisible pour qui venait d'écrire le code. Après avoir codé, on relit son
intention, pas ce qui est écrit.

## Décision

Toute nouvelle fonctionnalité ou correction de bug suit cet ordre, sans
raccourci :

1. **Coder**
2. **Tests automatisés** — étendre la suite existante, couvrir les cas limites
   et les garde-fous critiques
3. **Double relecture** — deux agents de revue lancés **en parallèle**, avec un
   **contexte neuf** (jamais un fork : le but est précisément de ne pas hériter
   des angles morts de celui qui a codé). Chacun reçoit un briefing complet et
   un angle distinct, typiquement :
   - l'un sur la correctness du nouveau code et ses cas limites
   - l'autre sur les régressions et effets de bord sur l'existant
4. **Traiter les retours** — vérifier chaque trouvaille dans le code avant de
   l'accepter ou de l'écarter ; un agent décrit ce qu'il a cru voir
5. **Bump de version + build + smoke test**
6. **Validation locale par Collins** — pas de push tant qu'il n'a pas confirmé
7. **Push + release**

Les étapes 3 et 4 précèdent le bump. Une version numérotée est un artefact de
livraison : on ne la crée pas avant que le code soit relu.

## Conséquences

**Ce qu'on gagne.** Les défauts de concurrence, les régressions sur du code
voisin et les cas limites non couverts sont attrapés avant la prod. Le coût
d'une relecture se compte en minutes, celui d'une régression en semaines de
diagnostic — l'incident `_MEI`/TLS en est la démonstration.

**Ce qu'on accepte.** Chaque livraison est plus lente et consomme des tokens
supplémentaires pour les deux relecteurs. C'est assumé : le parc est en
production, pas en développement.

**Ce qui reste à la charge de l'agent.** Les relecteurs n'ont aucun contexte :
un briefing incomplet produit une revue inutile. Il faut leur fournir le
contexte métier, le diff exact, l'historique des bugs voisins et ce qu'on
craint précisément. Et leur laisser la possibilité de ne rien trouver — un
relecteur qui valide tout ou qui invente des problèmes ne sert à rien.

**Hors périmètre.** Cet ADR ne s'applique pas rétroactivement aux versions déjà
en production.
