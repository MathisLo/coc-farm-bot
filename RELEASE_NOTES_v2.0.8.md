# CoC Farm Bot v2.0.8

Cette version cible les blocages signalés sur PC et reproduits sur le VPS : recherche répétée d'améliorations sans action, troupes parfois laissées dans la barre de combat, et lecture instable des ressources après un achat de rempart.

## Corrections et comportement

- **Bâtiments avant remparts.** Le menu des ouvriers est parcouru par prix décroissant, sans Hôtel de ville. Une liste immobile est reconnue plus tôt pour reprendre le cycle ; les prix OCR contradictoires sont refusés. Le panneau compact d'amélioration directe est reconnu avec vérification du titre, du coût, de la ressource et du bouton avant paiement. Le bot s'arrête sur un ouvrier libre pour les remparts.
- **Remparts uniques et groupes.** La ligne `x1` est exploitable même quand le nombre est mal lu. L'ouverture du mode groupe attend une interface stable ; les boutons et prix doivent concorder sur plusieurs captures. Le prix est recoupé entre or et élixir lorsque l'OCR perd un zéro, puis relu dans la vraie fenêtre de confirmation, individuelle ou groupée. Les lectures de réserves compactes ont été renforcées pour ne plus perdre le premier million après achat. La réserve minimale de 1 M d'or et de 1 M d'élixir reste obligatoire.
- **Armée complète.** La reconnaissance des électro-dragons sur fenêtre compacte continue lorsque leur compteur OCR est intermittent, mais exige finalement une carte vide. Les sorts Rage sont recherchés sur plusieurs captures et sur les deux dispositions possibles de la barre ; les quatre héros sont contrôlés séparément. Une carte de Rage attendue mais introuvable provoque une erreur explicite plutôt qu'un faux succès.
- **40 troupes temporaires.** Quand la carte rouge de l'événement est visible dans la barre de combat, le bot pose d'abord l'armée habituelle et les quatre héros, puis les 40 renforts par lots de cinq. Il vérifie `x0` et la carte grisée ; un écran de victoire n'est jamais confondu avec une carte vide. Les compteurs illisibles ou légèrement décalés sont suivis de façon bornée jusqu'à cette vérification. Aucune date d'événement n'est codée en dur : hors événement, la carte absente n'est pas sollicitée.
- **Cycle et diagnostic.** Les foreuses d'élixir noir sont collectées au village. Un avertissement apparaît au lancement si l'option « Améliorer les bâtiments » est décochée, ce qui expliquait le journal PC de 12 secondes sans recherche d'amélioration. Les dialogues reconnus « Réessayer » et « Recharger le jeu » peuvent être repris ; un message inconnu n'est pas cliqué à l'aveugle.

## Vérifications

- La suite complète compte 253 tests, dont 1 ignoré, sans échec. L'exécutable Windows a passé son autotest intégré (`ok=true`, `frozen=true`) ; le manifeste vérifie que les sources embarquées correspondent à celles testées.
- Sur TCD_VeNom, fenêtre de jeu 1323 x 744 : une Tour d'archères à 4 M d'or puis un Éradicateur de héros à 6 M d'élixir ont été lancés. L'Éradicateur affiche 9 h 59 d'amélioration et le nombre d'ouvriers libres est passé de 2 à 1 après achat.
- Des remparts `x1` ont été payés à 4 M en or et en élixir. Un nouvel essai réel a confirmé l'achat d'un rempart isolé à 4 M d'or malgré une lecture initiale à 400 000, puis le cycle a payé un autre rempart à 4 M d'élixir. Les captures des erreurs de lecture des réserves après ces achats sont couvertes par des tests de régression.
- Les attaques réelles ont confirmé, catégorie par catégorie, 10 électro-dragons, 1 dragon, 5 Rage et 4 héros, ainsi que le retour au village et la collecte des foreuses d'élixir noir.
- Des attaques réelles ont confirmé la carte temporaire `x40 → x0`, la pose vérifiée des 40 troupes et celle de l'armée habituelle, puis le retour au village. Les captures `x40`, `x37`, `x25` et `x35` décalé protègent la lecture du compteur par des tests de régression.
- Un cycle continu de 31,9 minutes sur TCD_VeNom s'est arrêté normalement au village : 6 attaques avec l'armée habituelle complète et les 40 renforts confirmés à chaque fois, 5 collectes de foreuses d'élixir noir, 3 paiements de remparts et aucune erreur du bot. Le contrôleur de validation a d'abord rejeté ce journal parce qu'il attendait 8 électro-dragons configurés au lieu des 10 réellement présents et posés ; ce contrôle a été corrigé séparément.
- Les cas critiques sont testés sur captures 1387 x 780, 1920 x 1080 et 2560 x 1440. Le jeu n'a été validé en direct qu'en 1323 x 744 ; les autres tailles peuvent demander un calibrage et un essai sur le PC concerné.

## Limites connues

- La reconnexion n'est pas universelle : seuls les dialogues reconnus avec commande de reprise sont automatisés.
- Le cycle complet a été validé sur le VPS, pas sur le PC de l'utilisateur ; son format de fenêtre et ses messages peuvent encore demander un essai local.
- Le cycle réel est exécuté depuis les sources de cette version ; l'exécutable publié a passé la construction et l'autotest, pas un cycle de jeu distinct.
- Certains essais intermédiaires de remparts se sont terminés en erreur après le paiement lorsque l'OCR perdait le premier million restant. La correction est couverte par les captures de régression et le cycle long ci-dessus ; une lecture future inconnue reste susceptible de reporter l'achat au cycle suivant.

Fermez l'ancienne application avant de lancer le `CoCFarmBot.exe` de cette publication. Réglages et journaux restent dans `%USERPROFILE%\CoCFarmBot`.

SHA-256 de `CoCFarmBot.exe` : `15b5a77cee07c006b6384ca9dacbb728a2308dd5757b40279c22bb2a7954596e`.
