# État du projet

## Version actuelle

La V1 est une application Windows locale. Elle sélectionne une fenêtre, capture son contenu via l'API Windows, lit deux zones de ressources grâce à l'OCR de Windows et, si les seuils sont atteints, envoie les points de déploiement à la fenêtre ciblée. La simulation est activée par défaut.

## Vérifié le 18 septembre 2026

- Le code Python se compile.
- L'OCR intégré lit correctement `123456` sur une image générée localement.
- L'exécutable démarre et le même auto-test OCR fonctionne dans l'exécutable.

## À vérifier avec Google Play Jeux PC

- La capture de la fenêtre du jeu avec `PrintWindow`.
- La lecture OCR sur les polices et la résolution réelles de Clash of Clans.
- La réception de clics par la fenêtre en arrière-plan.
- Les coordonnées des deux zones de butin et du déploiement des électro-dragons.

## Dépôt distant

Le dépôt Git local est prêt. La publication GitHub attend un accès GitHub sur cette machine, car `gh` n'est pas installé et aucun accès distant n'est configuré.
