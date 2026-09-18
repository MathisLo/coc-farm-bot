# CoC Farm Bot — prototype local

Application Windows autonome pour lire le butin affiché dans une fenêtre Google Play Jeux PC et déployer une série d'électro-dragons selon une configuration enregistrée localement.

## Lancer depuis le dossier projet

```powershell
.\.venv\Scripts\python.exe main.py
```

Choisis la fenêtre Google Play Jeux dans la liste, puis utilise **Capturer et lire**. La reconnaissance utilise l'OCR intégré à Windows. Renseigne ensuite les deux zones de butin, les seuils et les coordonnées des dragons (relatives à la fenêtre du jeu). Le mode **Simulation** est actif par défaut et ne clique jamais.

Une fois les valeurs vérifiées, décoche Simulation et lance le bot. Il ne déplace jamais le curseur Windows : les clics sont envoyés à la fenêtre sélectionnée. Le bouton Arrêter interrompt la boucle immédiatement.

## Construire l'exécutable

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name CoCFarmBot main.py
```

Le fichier exécutable est créé dans `dist\CoCFarmBot.exe`.

## Limites de cette V1

Google Play Jeux PC n'expose pas ADB sur cette installation. La V1 utilise donc le pilote de fenêtre Windows. Si le jeu ignore les clics envoyés en arrière-plan, le journal de l'application le signalera : il faudra alors un canal de contrôle fourni par le client, sans modifier le comportement du bot.
