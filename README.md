# CoC Farm Bot

Application Windows pour Google Play Jeux PC. Elle lit le butin des bases adverses, cherche une base qui atteint les seuils configurés, puis déploie l’armée choisie. Les commandes sont envoyées à la fenêtre du jeu sans déplacer la souris Windows.

## Démarrer

Lancer [l’exécutable](dist/CoCFarmBot.exe) ou, depuis le dossier du projet :

```powershell
.\.venv\Scripts\python.exe main.py
```

Dans l’application :

1. Choisir la fenêtre Clash of Clans. **Détecter** actualise la liste ; **Lire l’écran** affiche une capture et les ressources lues.
2. Régler les seuils d’or et d’élixir, la marge, le nombre de dragons et d’électro-dragons, puis les options du cycle.
3. Cliquer sur **Enregistrer** pour garder ces réglages, ou sur **Lancer le farm** pour les enregistrer et démarrer.
4. **Arrêter** interrompt la boucle. Les événements sont affichés dans le journal.

La **simulation** recherche des bases et lit leur butin sans déployer de troupes ni améliorer de remparts. En mode réel, l’option remparts conserve au moins 1 000 000 d’or et 1 000 000 d’élixir en réserve avant chaque dépense. Si les montants ou la confirmation sont illisibles, les améliorations s’arrêtent.

## Construire l’exécutable

```powershell
.\BUILD.ps1
```

Le résultat est `dist\CoCFarmBot.exe`. Le script place les fichiers temporaires de construction dans `build\`.

## Fichiers utiles

- `main.py` : interface et automatisation du jeu.
- `requirements.txt` : dépendances Python.
- `BUILD.ps1` : création de l’exécutable Windows.
- `%USERPROFILE%\CoCFarmBot\config-v2.json` : réglages personnels, repris automatiquement depuis les versions précédentes.
- `%USERPROFILE%\CoCFarmBot\bot.log` : journal détaillé.
- `%USERPROFILE%\CoCFarmBot\account_snapshot.json` : dernier relevé demandé via **Relever le profil**.

Le suivi des fonctionnalités et des validations se trouve dans [Notion](https://app.notion.com/p/3dccca7fe8b78060a5c3ca2aa4b73fa8). Le dépôt GitHub contient les sources ; les fichiers de construction et les captures de diagnostic restent locaux.
