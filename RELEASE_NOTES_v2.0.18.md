# CoC Farm Bot v2.0.18

- Trois choix indépendants dans **Cycle** permettent d’ignorer l’Éradicateur de héros, la Catapulte explosive et la Bougie incandescente. Les réglages sont conservés après fermeture et s’appliquent aussi aux améliorations ponctuelles.
- Les clics maintiennent l’appui 80 ms pour être vus par le jeu. L’arrêt interrompt l’attente et relâche toujours la souris.
- Le bot attend deux captures concordantes des menus et du village avant de poursuivre. Le retour au village utilise une attente adaptée à l’écran affiché.
- Les relectures OCR identiques sont évitées sur une même capture, et la lecture initiale des ouvriers est raccourcie. Les captures utilisées pour autoriser une dépense restent indépendantes.

Sur une capture réelle de PC-FIXE, trois mesures par version donnent une recherche médiane dans la liste des ouvriers de 47,2 s avant et 22,4 s après, avec le même résultat. Ce gain de 52,6 % concerne la lecture de la liste, pas la durée totale du cycle ou du combat.

Validation : sauvegarde et rechargement des choix dans le lanceur WebView ; six ouvertures/fermetures du menu confirmées en jeu ; reproduction du clic instantané manqué dans une fenêtre Windows lisant les entrées à 30 images par seconde, puis réussite avec le nouvel appui. Aucun bâtiment ni rempart acheté pendant ce contrôle des clics.
