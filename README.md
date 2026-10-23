# ARPEJ IDF — Jeunes actifs

Surveillance des résidences **explicitement identifiées** « jeunes actifs » en Île-de-France.

## Mise en place

Remplacer `monitor.py`, `requirements.txt`, `.github/workflows/monitor.yml` et ajouter `idf_residences.json` dans le dépôt GitHub. Conserver le secret `DISCORD_WEBHOOK_URL`.

Le script initialise `state_idf_jeunes_actifs.json` au premier scan (aucune alerte), puis envoie des alertes pour les augmentations de disponibilité. L'ancien `state.json` est ignoré intentionnellement.

## Limites à connaître

- Le site publie toutes ses résidences dans le HTML même quand les filtres URL sont fournis. Le filtrage est donc appliqué dans le script.
- Le référentiel `idf_residences.json` est une **photographie des 88 résidences franciliennes** identifiées dans le premier scan fourni. Toute nouvelle résidence non répertoriée sera signalée dans les logs et ignorée jusqu'à vérification et ajout dans le référentiel.
- Les résidences mixtes ou accueillant des jeunes actifs sans la mention « jeunes actifs » dans leur nom ou URL sont ignorées volontairement pour éviter les fausses alertes. Pour les inclure, vérifier le public visé sur leur fiche et étendre `is_young_active`.
- La disponibilité est mesurée **par résidence**, pas par appartement individuel.
- La structure HTML peut changer : une exécution réussie ne garantit pas l'exactitude des extractions, à vérifier dans les logs.
- Les exécutions GitHub Actions peuvent être retardées ou omises.

## Mention « réservé(e) » dans Discord

Pour chaque **nouvelle disponibilité**, le script ouvre la fiche de la résidence et tente de détecter une mention du type « Résidence réservée aux ... » ou « Résidence exclusivement réservée à ... » près du titre. Il la joint à la notification Discord. Si aucune mention n'est détectée, il ne suppose pas pour autant que l'accès est libre. Si la fiche est inaccessible, il affiche « Conditions d'accès non vérifiées ».

La mention **réservée** décrit une éventuelle restriction d'éligibilité (public/établissement), **pas** le fait qu'un logement soit déjà loué ou indisponible. Aucun appel supplémentaire à la fiche n'est effectué lorsqu'aucune disponibilité nouvelle n'est notifiée.
