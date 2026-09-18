# CoC Farm Bot — V1 locale

Application Windows autonome pour lire le butin affiché dans une fenêtre Google Play Jeux PC et déployer une série d'électro-dragons selon une configuration enregistrée localement.

## Lancer depuis le dossier projet

```powershell
.\.venv\Scripts\python.exe main.py
```

Choisis la fenêtre Clash of Clans, clique sur **Capturer**, puis calibre l'application directement sur son aperçu : trace la zone de l'or, trace la zone de l'élixir, choisis l'icône des électro-dragons et ajoute les points où les déposer. Les coordonnées sont enregistrées en pourcentage et restent valides si la fenêtre change de taille.

Le mode **Simulation** est actif par défaut et ne clique jamais. Utilise **Tester l'OCR** : les deux valeurs doivent être correctes avant de le désactiver. L'application ne déplace jamais le curseur Windows : les clics sont envoyés à la fenêtre Clash. Le bouton Arrêter interrompt la boucle immédiatement.

## Recherche et attaque électro-dragons

Le bouton **Lancer farm** ouvre le parcours multijoueur, lit l'or et l'élixir disponibles sur chaque base adverse, puis passe à la suivante tant que les seuils configurés ne sont pas atteints. Une base acceptée sélectionne la case des électro-dragons et les répartit sur huit points extérieurs : quatre à gauche et quatre à droite du terrain. Ces coordonnées restent sur le pourtour autorisé, hors de la zone rouge de la base. Garde **Simulation** active pour vérifier les décisions dans le journal avant d’autoriser les clics.

## Relever le compte

Depuis l'écran de village, clique sur **Relever le profil**. L'application lit le pseudo, le niveau, l'or, l'élixir, l'élixir noir, les gemmes, les ouvriers de laboratoire et les ouvriers. Le dernier relevé est enregistré dans `%USERPROFILE%\CoCFarmBot\account_snapshot.json` avec les lectures OCR brutes pour diagnostic.

## Construire l'exécutable

```powershell
.\BUILD.ps1
```

Le fichier exécutable est créé dans `dist\CoCFarmBot-V1_6.exe`.

## Limites de cette V1

Google Play Jeux PC n'expose pas ADB sur cette installation. La V1 utilise donc le pilote de fenêtre Windows, inspiré de `nullmacro_src`. Si le jeu refuse une capture ou des clics envoyés en arrière-plan, le journal de l'application le signalera explicitement.
