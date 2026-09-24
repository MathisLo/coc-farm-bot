# CoC Farm Bot v2.0.7

Cette version fiabilise le cycle de farming sur les fenêtres de jeu compactes et donne la priorité aux améliorations de bâtiments avant les remparts. Elle ajoute aussi des contrôles plus précis pour les ouvriers, la collecte et les dépenses.

## Corrections et options

- Déploiement : le bot repère la carte d'électro-dragon au format compact, teste un point de pose légal, puis confirme la baisse du compteur avant de continuer. Les Rage sont relus après leurs animations et les quatre héros sont vérifiés séparément.
- Village : collecte des mines, extracteurs et foreuses d'élixir noir au début de chaque tour.
- Bâtiments : recherche du bâtiment payable le plus cher avant les remparts, exclusion de l'Hôtel de ville, vérification du titre, du coût, de la ressource, des réserves et du nombre d'ouvriers avant/après achat. Un ouvrier normal reste réservé. Après deux lignes instables, le bot reprend les remparts et les attaques au lieu de bloquer la boucle.
- Remparts : une ligne `x1` est prise en compte comme un rempart individuel ; le paiement n'est envoyé que si le coût est confirmé et s'il reste au moins 1 M d'or et 1 M d'élixir. Le compteur d'ouvriers ignore celui de l'ouvrier gobelin temporaire.
- Fenêtre : le calibrage affiche la taille intérieure capturée et conserve le format avec les positions. Les clics sont refusés si le format change. Le bot peut reprendre après les dialogues de reconnexion dont le bouton Réessayer ou Recharger est reconnu ; un message inconnu reste un arrêt prudent.
- Diagnostic : l'outil de validation en console peut tester séparément collecte, bâtiments, remparts, une attaque ou un cycle chronométré.

## Vérifications effectuées

- 218 tests exécutés, 1 ignoré, aucun échec. Captures de régression utilisées pour 1920 x 1080, 2560 x 1440 et 1387 x 780.
- Cycle réel sur TCD_VeNom, fenêtre 1323 x 744 : 34,5 minutes et 3 attaques complètes. Chaque attaque a confirmé 10 électro-dragons, 1 dragon, 4 héros et 5 Rage ; le résultat a été reconnu et le bot est revenu au village.
- Foreuse d'élixir noir collectée à chacun des quatre tours observés. Une tour d'archers lancée pour 4 M d'or, avec passage vérifié de 3 à 2 ouvriers libres. Un rempart amélioré pour 4 M d'élixir, avec 1 132 889 d'élixir conservé.
- Une autre amélioration longue avait déjà été confirmée sur ce village pendant la préparation : catapulte explosive pour 4 M d'élixir.

## Limites connues

- Le passage réel de 2 à 1 ouvrier libre n'a pas été obtenu pendant ce cycle : les autres propositions étaient non payables ou trop instables pour être sélectionnées sans risque. Le bot les refuse sans dépenser.
- Un rempart unique `x1` a été détecté en jeu, mais son coût de 4 M ne respectait pas alors la réserve demandée ; son achat n'a donc pas été validé en direct.
- Les résolutions 1080p, 1440p et 780p ont été vérifiées sur captures, pas par un cycle réel sur chaque écran. Le cycle réel ci-dessus portait sur 1323 x 744. Une taille ou interface différente peut nécessiter un calibrage et un essai local.
- La reconnexion est testée pour les dialogues reconnus, pas pour n'importe quel message possible.

Téléchargement : `CoCFarmBot.exe` dans les fichiers de cette publication. Fermez une ancienne instance avant de la remplacer. Les réglages et journaux restent dans `%USERPROFILE%\CoCFarmBot`.

SHA-256 de `CoCFarmBot.exe` : `36aaaa0882226325a86bbc87c9e916bf411024e617134c341e69b125f4eb4d28`.
