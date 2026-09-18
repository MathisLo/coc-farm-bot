# CoC Farm Bot — V1 locale

Application Windows autonome pour lire le butin affiché dans une fenêtre Google Play Jeux PC et déployer une série d'électro-dragons selon une configuration enregistrée localement.

## Lancer depuis le dossier projet

```powershell
.\.venv\Scripts\python.exe main.py
```

Choisis la fenêtre Clash of Clans, clique sur **Capturer**, puis calibre l'application directement sur son aperçu : trace la zone de l'or, trace la zone de l'élixir, choisis l'icône des électro-dragons et ajoute les points où les déposer. Les coordonnées sont enregistrées en pourcentage et restent valides si la fenêtre change de taille.

Le mode **Simulation** est actif par défaut et ne clique jamais. Utilise **Tester l'OCR** : les deux valeurs doivent être correctes avant de le désactiver. L'application ne déplace jamais le curseur Windows : les clics sont envoyés à la fenêtre Clash. Le bouton Arrêter interrompt la boucle immédiatement.

## Relever le compte

Depuis l'écran de village, clique sur **Relever le profil**. L'application lit le pseudo, le niveau, l'or, l'élixir, l'élixir noir, les gemmes, les ouvriers de laboratoire et les ouvriers. Le dernier relevé est enregistré dans `%USERPROFILE%\CoCFarmBot\account_snapshot.json` avec les lectures OCR brutes pour diagnostic.

## Construire l'exécutable

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name CoCFarmBot main.py
```

Le fichier exécutable est créé dans `dist\CoCFarmBot.exe`.

## Limites de cette V1

Google Play Jeux PC n'expose pas ADB sur cette installation. La V1 utilise donc le pilote de fenêtre Windows, inspiré de `nullmacro_src`. Si le jeu refuse une capture ou des clics envoyés en arrière-plan, le journal de l'application le signalera explicitement.
