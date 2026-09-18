# CoC Farm Bot — V1 locale

Application Windows autonome pour lire le butin affiché dans une fenêtre Google Play Jeux PC et déployer une série d'électro-dragons selon une configuration enregistrée localement.

## Lancer depuis le dossier projet

```powershell
.\.venv\Scripts\python.exe main.py
```

Choisis la fenêtre Clash of Clans, clique sur **Capturer**, puis calibre l'application directement sur son aperçu : trace la zone de l'or, trace la zone de l'élixir, choisis l'icône des électro-dragons et ajoute les points où les déposer. Les coordonnées sont enregistrées en pourcentage et restent valides si la fenêtre change de taille.

Le mode **Simulation** est actif par défaut et ne clique jamais. Utilise **Tester l'OCR** : les deux valeurs doivent être correctes avant de le désactiver. L'application ne déplace jamais le curseur Windows : les clics sont envoyés à la fenêtre Clash. Le bouton Arrêter interrompt la boucle immédiatement.

## Recherche et attaque électro-dragons

Le bouton **Lancer farm** ouvre le parcours multijoueur, lit l'or et l'élixir disponibles sur chaque base adverse, puis passe à la suivante tant que les seuils configurés ne sont pas atteints. Une base acceptée sélectionne la case des électro-dragons et les pose huit fois sur le pourtour latéral : quatre poses à gauche et quatre à droite. Les deux premières poses de chaque flanc partagent volontairement une position déjà validée afin de rester hors de la zone rouge, quelle que soit la forme de la base.

La **Marge %** réduit les deux seuils de ce pourcentage. Par exemple, avec 500 000 et 5 %, une base est acceptée à partir de 475 000 or et 475 000 élixir. Le mode réel est désormais le réglage initial. Coche **Mode simulation (sans pose)** seulement pour vérifier le filtre sans envoyer les électro-dragons.

## Composition et cycle

Règle le nombre d’**Électro-dragons** et de **Dragons** dans l’application. Le bot limite chaque catégorie au nombre indiqué, puis pose les trois héros cochés dans la barre. Avec **Remparts jusqu’à 1 M restants**, il ouvre les cinq ouvriers, cherche un rempart, lit les deux coûts affichés et améliore autant de remparts que possible sans faire passer l’or ou l’élixir sous 1 000 000. Toute lecture ou confirmation absente stoppe cette étape. Avec **Enchaîner les attaques**, il attend l’écran de résultat, revient au village et reprend ce cycle.

## Relever le compte

Depuis l'écran de village, clique sur **Relever le profil**. L'application lit le pseudo, le niveau, l'or, l'élixir, l'élixir noir, les gemmes, les ouvriers de laboratoire et les ouvriers. Le dernier relevé est enregistré dans `%USERPROFILE%\CoCFarmBot\account_snapshot.json` avec les lectures OCR brutes pour diagnostic.

## Construire l'exécutable

```powershell
.\BUILD.ps1
```

Le fichier exécutable est créé dans `dist\CoCFarmBot-V1_9.exe`.

## Limites de cette V1

Google Play Jeux PC n'expose pas ADB sur cette installation. La V1 utilise donc le pilote de fenêtre Windows, inspiré de `nullmacro_src`. Si le jeu refuse une capture ou des clics envoyés en arrière-plan, le journal de l'application le signalera explicitement.
