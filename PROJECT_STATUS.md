# État du projet

## Version actuelle

La V1 est une application Windows locale inspirée de la structure de `nullmacro_src`. Elle détecte Clash of Clans automatiquement, capture la fenêtre entière, permet de calibrer les zones de butin, l'icône des électro-dragons et les points de déploiement directement sur l'aperçu, puis lit les deux ressources avec l'OCR de Windows. La simulation est activée par défaut.

## Vérifié le 18 septembre 2026

- Le code Python se compile.
- L'OCR intégré lit correctement `123456` sur une image générée localement.
- La V1 calibrable remplace les coordonnées fixes qui rendaient la lecture réelle impossible.
- L'OCR intégré lit `123456` dans un test local intégré à l'exécutable.
- L'exécutable démarre sans erreur en arrière-plan.
- La capture réelle de `Clash of Clans - TCDVeNom` fonctionne en arrière-plan en 1920×1080, sans utiliser la souris.
- L'OCR Windows reçoit également cette capture. La calibration du butin doit être faite sur l'écran d'une base adverse, car l'écran de village ne présente pas les deux valeurs de butin recherchées.
- Le relevé du profil de village est validé en capture réelle et dans l'exécutable `CoCFarmBot-V1_3.exe` : pseudo, niveau, or, élixir, élixir noir, gemmes, ouvriers de laboratoire et ouvriers.
- Le parcours d'attaque est testé sur Google Play Jeux PC : ouverture du menu, recherche multijoueur, lecture de trois bases adverses, sélection d'un électro-dragon et pose validée (compteur 8 vers 7). Le bouton **Lancer farm** intègre ce parcours avec le filtre 500 000 or / 500 000 élixir. La V1.5 attend aussi la mention « Butin disponible » avant toute décision et lit les chiffres avec un second passage OCR binarisé.
- V1.6 : le déploiement par défaut est limité au pourtour latéral autorisé, avec quatre points à gauche et quatre à droite. Une recherche réelle a trouvé une base à 784 163 or et 701 043 élixir ; les six poses latérales initiales ont été acceptées. Deux points trop bas ont été rejetés par la zone rouge, donc ils ont été retirés. Les deux essais vers le haut ont ouvert une interface du jeu au lieu de poser des troupes ; ils ont eux aussi été retirés. La version finale garde exclusivement les flancs et ajoute deux positions intermédiaires pour compléter les huit poses.
- V1.7 : correction du blocage de pose. La configuration V1.6 enregistrait encore `Simulation=true`, donc elle arrêtait la boucle avant de sélectionner les électro-dragons. La migration passe désormais la configuration au mode réel et l'interface indique clairement le mode choisi. Les huit poses utilisent uniquement trois positions latérales validées : chaque flanc reçoit quatre dragons, dont deux au même point sûr. Une marge réglable de 0 à 25 % s'applique aux deux seuils ; avec 500 000 et 5 %, l'attaque commence à 475 000 or et 475 000 élixir. Compilation, tests de décision et exécutable V1.7 validés.

## À vérifier avec Google Play Jeux PC

- La capture de la fenêtre du jeu avec `PrintWindow`.
- La lecture OCR sur les polices et la résolution réelles de Clash of Clans.
- La réception de clics par la fenêtre en arrière-plan.
- Les coordonnées des deux zones de butin et du déploiement des électro-dragons.

## Dépôt distant

Le projet est publié sur https://github.com/MathisLo/coc-farm-bot.
