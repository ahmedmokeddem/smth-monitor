# SMTH Monitor — Île-de-France / jeunes actifs

Surveille automatiquement **toutes les résidences listées par SMTH**, puis ouvre **chaque fiche à chaque scan** pour déterminer :

- l'éligibilité depuis **« Logements clés en main pour : Jeunes actifs »** ;
- la région depuis le **code postal francilien** (75, 77, 78, 91, 92, 93, 94, 95) ;
- le nombre de logements depuis le champ **« Disponibilité »** ;
- la mention **« Accès limité » / « Réservé à »** lorsqu'elle figure dans l'introduction de la fiche.

Le fichier `idf_residences.json` **n'est plus utilisé**. Aucune liste de résidences à maintenir.

## Installation GitHub

1. Remplacer `monitor.py`, `requirements.txt` et `.github/workflows/monitor.yml` dans ton dépôt.
2. Supprimer `idf_residences.json` (facultatif : il n'est plus utilisé).
3. Conserver le secret GitHub Actions `DISCORD_WEBHOOK_URL`.
4. Conserver `state_idf_jeunes_actifs.json` pour éviter de recevoir à nouveau les alertes existantes. Si ce fichier n'existe pas, le premier scan est une initialisation sans alertes.
5. Ouvrir **Actions → SMTH monitoring → Run workflow**.

Par défaut : toutes les **15 minutes**. Pour réduire le trafic, ne pas activer plusieurs workflows surveillant le site en parallèle. Environ 100 fiches HTTP sont consultées par scan, espacées d'environ 0,7 s.

**Avertissement :** parser de HTML fragile si SMTH modifie son site. Le code et des tests synthétiques ont été vérifiés, mais pas d'exécution réseau directe depuis l'environnement de construction. Examiner les logs du premier scan. Les fiches incomplètes ne sont pas converties en disponibilité zéro.

## Comportement

- Premier scan sans état : enregistrer sans notifier.
- 0 → 1, 1 → 2 : notifier Discord.
- Baisse ou stabilité : pas de notification.
- Résidence nouvellement connue : si des logements sont disponibles, notifier après l'initialisation.
- Les anciennes entrées restent dans l'historique même si une résidence disparaît.

Pense à vérifier les conditions d'utilisation du site et à adapter la fréquence si nécessaire.
