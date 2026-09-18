# État du projet

## Version actuelle

La V1 est une application Windows locale inspirée de la structure de `nullmacro_src`. Elle détecte Clash of Clans automatiquement, capture la fenêtre entière, permet de calibrer les zones de butin et les points de déploiement directement sur l'aperçu, puis lit les deux ressources avec l'OCR de Windows. La simulation est activée par défaut.

## Vérifié le 18 septembre 2026

- Le code Python se compile.
- L'OCR intégré lit correctement `123456` sur une image générée localement.
- La V1 calibrable remplace les coordonnées fixes qui rendaient la lecture réelle impossible.
- L'OCR intégré lit `123456` dans un test local intégré à l'exécutable.
- L'exécutable démarre sans erreur en arrière-plan.

## À vérifier avec Google Play Jeux PC

- La capture de la fenêtre du jeu avec `PrintWindow`.
- La lecture OCR sur les polices et la résolution réelles de Clash of Clans.
- La réception de clics par la fenêtre en arrière-plan.
- Les coordonnées des deux zones de butin et du déploiement des électro-dragons.

## Dépôt distant

Le dépôt Git local est prêt. La publication GitHub attend un accès GitHub sur cette machine, car `gh` n'est pas installé et aucun accès distant n'est configuré.
