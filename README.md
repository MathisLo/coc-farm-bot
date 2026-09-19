# CoC Farm Bot

Application Windows pour Google Play Jeux PC. Elle lit le butin des bases adverses, cherche une base qui atteint les seuils configurés, puis déploie l’armée choisie. Les commandes sont envoyées à la fenêtre du jeu sans déplacer la souris Windows.

## Démarrer

Télécharger puis lancer [CoCFarmBot.exe depuis la dernière Release GitHub](https://github.com/MathisLo/coc-farm-bot/releases/latest/download/CoCFarmBot.exe) ou, depuis le dossier du projet :

```powershell
.\.venv\Scripts\python.exe main.py
```

Dans l’application :

1. Choisir la fenêtre Clash of Clans. **Détecter** actualise la liste ; **Lire l’écran** affiche une capture et les ressources lues.
2. Régler les seuils d’or et d’élixir, la marge, les nombres de troupes prévus et les options du cycle.
3. Cliquer sur **Enregistrer** pour garder ces réglages, ou sur **Lancer le farm** pour les enregistrer et démarrer.
4. **Arrêter** interrompt la boucle. Les événements sont affichés dans le journal.

La **simulation** clique réellement pour rechercher et passer les bases, mais ne déploie pas de troupes et n’améliore pas de remparts. En mode réel, le bot lit le nombre de troupes présentes dans la barre de combat, les répartit sur une seule ligne en haut à gauche et envoie les héros sur cette même ligne juste derrière. Les troupes sont posées par groupes de trois maximum, à 60 ms d’intervalle hors capture et clics. Deux lectures concordantes du compteur vérifient chaque groupe avant de continuer. Un résultat illisible ou incohérent arrête la pose ; un simple changement de pixels n’est pas une confirmation. Les nombres saisis dans l’interface servent de prévision ; toutes les unités disponibles des deux types pris en charge sont envoyées. La pose des trois héros est également vérifiée visuellement.

**Arrêter** bloque les nouveaux clics de toutes les actions, y compris les héros et les confirmations de remparts. Un clic déjà envoyé est relâché. Les lectures OCR sont annulables et limitées à huit secondes par appel ; une base dont l’écran ou le butin reste illisible dispose d’un budget de 35 secondes. Ensuite, sa capture est conservée dans `%USERPROFILE%\CoCFarmBot\unread-enemies` et le bot passe à la suivante uniquement si le bouton Suivant est reconnu sur une nouvelle capture. Sinon, il s’arrête sans clic. Avec le réglage « or ou élixir », une seule ressource lisible atteignant son seuil suffit ; le réglage exigeant les deux ressources conserve ses deux vérifications. **Lire l’écran** et **Relever le profil** travaillent en arrière-plan : l’interface et le bouton Arrêter restent disponibles. Une seule opération est autorisée à la fois, et les réglages utilisés ne changent pas en cours de cycle.

## Adapter les positions

Le profil fourni vise l’interface française en **16:9**, avec dragons, électro-dragons et trois héros. Les captures et les clics utilisent la zone intérieure de la fenêtre, sans barre de titre. Les dimensions sont relues à chaque capture et chaque clic. Un redimensionnement entre la lecture et l’action interrompt le bot ; relancer une fois la fenêtre stabilisée. Si son format diffère du calibrage, aucun clic n’est envoyé.

Le bouton **Calibrer les positions…** permet d’adapter les boutons, les zones de lecture, les cartes de troupes, les héros et les seize points de déploiement :

1. Afficher le menu concerné dans le jeu, puis ouvrir le calibrage.
2. Choisir l’élément dans la liste. Cliquer sur l’aperçu pour placer un point ; tracer un rectangle pour définir une zone de lecture.
3. Utiliser **Actualiser la capture** après avoir changé de menu, ou **Charger une capture…** pour une image enregistrée au même format.
4. Enregistrer. Les positions et le format sont conservés avec les autres réglages. **Réinitialiser cet élément** restaure sa position d’origine.

Les clics dans l’aperçu ne commandent jamais le jeu. Pour déplacer une troupe, ajuster sa sélection, son compteur et son icône. Pour un héros, ajuster sa sélection, son icône et sa barre de vie. Les réglages individuels sont utilisés tels quels ; les héros non personnalisés conservent le décalage automatique lié à l’engin de siège. Il ne s’agit pas d’une reconnaissance automatique de toute composition d’armée ou de toute interface.

L’option du cycle améliore les remparts entre les attaques. Le bouton **Améliorer les remparts** lance cette action seule. Le bot repère la ligne des remparts dans le menu des ouvriers, utilise **Améliorer plus** pour former le plus grand lot payable et conserve au moins 1 000 000 d’or et 1 000 000 d’élixir avant chaque dépense. Comme les coûts sont par paliers, il peut rester un peu plus d’un million si une autre amélioration ferait passer sous ce seuil. Si les montants, l’écran ou la confirmation sont illisibles, il s’arrête sans confirmer la dépense.

Les commandes de jeu nécessitent une fenêtre Clash accessible. Si le jeu change de menu pendant une action, arrêtez le bot et revenez au village avant de relancer les remparts.

## Construire l’exécutable

```powershell
.\BUILD.ps1
```

Le résultat est `dist\CoCFarmBot.exe`. Le script exécute les tests, construit dans `build\release`, puis lance un autotest de l’exécutable sur une image synthétique, sans ouvrir le bot ni agir dans le jeu. Il vérifie les empreintes des sources embarquées avant de remplacer l’ancien exécutable. `dist\release-check.json` conserve le résultat et `dist\build-manifest.json` contient les empreintes des sources et de l’exécutable.

Si les dépendances sont déjà installées : `./BUILD.ps1 -SkipDependencyInstall`. Un échec d’installation, de test ou de construction interrompt le script. Fermer l’ancienne application avant de remplacer son exécutable.

## Vérifier sans agir dans le jeu

```powershell
.\.venv\Scripts\python.exe -B -m unittest -v test_main test_regressions test_windows_integration
```

Les tests couvrent l’arrêt avant les clics, les dimensions et changements de fenêtre, les compteurs, les délais OCR, le calibrage et la réactivité de l’interface. `testdata` contient les extraits réels reproduisant les erreurs de réserves, le compteur sélectionné « x1 » et le décalage des boutons lorsque des anneaux de rempart sont disponibles. Les tests Windows utilisent ces images et des fenêtres de test, sans agir dans le jeu.

La vérification réelle du 19 septembre 2026 a confirmé un déploiement de 8 électro-dragons, 1 dragon et 3 héros, suivi du retour au village, puis 13 améliorations de remparts dans un cycle. Un dernier essai a confirmé une amélioration supplémentaire, puis l’arrêt faute de budget : 1 045 191 or et 1 429 534 élixir conservés. Ce relevé décrit ces tests sur l’interface française 1920×1080, pas une garantie pour toute composition ou interface.

Les chiffres blancs sont isolés des fonds colorés pour l’OCR. Le compteur « x1 », parfois ignoré par Windows, dispose aussi d’une reconnaissance des deux caractères. Avant chaque attaque retenue en mode réel, le bot dézoome avec la molette, puis reprend une capture avant de poser les troupes. Les points de pose refusés sont écartés pour le reste du déploiement de cette troupe. Les boutons Ajouter et les paiements en or/élixir sont détectés sur chaque nouvelle capture. Chaque ajout est confirmé par le prix du groupe avant le clic suivant, même lorsque le bouton +10 disparaît et déplace la rangée. Les anneaux ne sont jamais sélectionnés. Le dernier rempart utilise sa confirmation individuelle. Une ligne de menu doit présenter son étiquette verte et son libellé : un nom visible derrière le menu transparent ne suffit pas.

Pendant l’événement, le bot attend l’apparition des trois cartes puis choisit **l’or ou l’élixir en priorité** puis les **tickets d’événement** si aucune ressource n’est reconnue. **Aucune troupe d’événement n’est sélectionnée** ; une carte illisible ne déclenche aucun clic. Il confirme la fermeture de la fenêtre avant de reprendre les autres commandes. Cette surveillance continue après le déploiement, jusqu’au retour au village. Une fenêtre persistante provoque un arrêt. Les commandes de dézoom et de récompense respectent le bouton **Arrêter**.

La reconnaissance des héros exige une barre de vie verte horizontale sous un bord sombre : l’herbe derrière une carte non déployée ne suffit plus à considérer le héros comme posé. Le test réel a reproduit le faux positif sur la reine, puis confirmé la pose des trois héros après correction. Le dézoom a été vérifié depuis une vue fortement agrandie ; les choix automatiques ont été vérifiés sur des cartes d’or et d’élixir.

## Fichiers utiles

- `main.py` : interface et automatisation du jeu.
- `calibration.py` : édition des positions sur une capture.
- `test_main.py`, `test_regressions.py`, `test_windows_integration.py` : validations locales.
- `requirements.txt` : dépendances Python.
- `BUILD.ps1` : création de l’exécutable Windows.
- `%USERPROFILE%\CoCFarmBot\config-v2.json` : réglages personnels, repris automatiquement depuis les versions précédentes.
- `%USERPROFILE%\CoCFarmBot\bot.log` : journal détaillé.
- `%USERPROFILE%\CoCFarmBot\account_snapshot.json` : dernier relevé demandé via **Relever le profil**.

Le suivi des fonctionnalités et des validations se trouve dans [Notion](https://app.notion.com/p/3dccca7fe8b78060a5c3ca2aa4b73fa8). Le dépôt GitHub contient les sources et chaque mise à jour publiée fournit un exécutable Windows testé dans les Releases. Les fichiers de construction et les captures de diagnostic restent locaux.
# Statistiques de récolte

L'interface « Le coffre de guerre » regroupe les trois ressources dans des cartes colorées avec emojis. Les réglages se trouvent dans les onglets Butin, Armée et Cycle ; le journal et l'aperçu du jeu ont leurs propres onglets. Les commandes Lancer, Arrêter et Améliorer les remparts restent en bas de la fenêtre. Taille minimale : 1040 × 860.

L'application affiche les cumuls d'or, d'élixir et d'élixir noir ainsi que le nombre de combats comptabilisés. Le suivi commence avec cette version : les anciennes récoltes ne sont pas reconstituées.

Les gains sont lus sur le résultat final du combat, avec le bonus de ligue. Les récompenses d'événement déjà incluses dans ce résultat ne sont pas ajoutées une seconde fois. Les dépenses de remparts ne soustraient rien à ces cumuls. Il s'agit du butin annoncé par le jeu, qui peut dépasser la place restante dans les réserves.

Les totaux sont sauvegardés dans `%USERPROFILE%\CoCFarmBot\farm-stats.json` et restaurés au lancement. Même en mode attaque unique, le bot attend le résultat pour le comptabiliser. Si la lecture reste incertaine, le résultat est conservé dans `unread-results` sans ajouter de gains aux totaux, puis le cycle reprend. Un résultat déjà enregistré n'est pas recompté. Un combat quitté manuellement avant sa lecture ne peut pas être reconstitué.


Les améliorations conseillées conservent au moins un ouvrier libre et un million d’or et d’élixir. Le bot parcourt toute la liste, recommandations puis autres améliorations. Il conserve ses ressources pour les bâtiments tant que plusieurs ouvriers restent libres. Les remparts automatiques attendent qu’il ne reste qu’un ouvrier libre. L’HDV attend que tous les autres travaux, remparts compris, soient confirmés terminés et qu’aucun ouvrier ne travaille encore.


## Validation des corrections du 19 septembre 2026

Les essais réels ont utilisé la capture et les messages de fenêtre en arrière-plan, sans activer le jeu ni déplacer la souris. Le jeu doit rester lancé et capable de produire ses images.

- Remparts : 17 améliorations consécutives, puis arrêt avec 1 428 809 or et 1 497 947 élixir (`diagnostics/upgrades_no_hdv.png`).
- Amélioration conseillée : piège à ressort à 500 000 or, compteur vérifié de 4 à 3 ouvriers libres ; réserves finales de 1 348 627 or et 2 333 092 élixir (`diagnostics/spring_verified_end.png`). Le HDV est exclu de la sélection et bloqué à la confirmation. Le dernier ouvrier est protégé par les tests du parcours d’amélioration et du contrôle de budget.
- Combat : 8 électro-dragons, 1 dragon et 3 héros confirmés automatiquement ; carte de 289 429 élixir choisie devant deux troupes d’événement (`diagnostics/strict_event_cycle.log`, `diagnostics/strict_event_card_2.png`). La priorité des tickets en l’absence de ressource et l’absence de repli sur une troupe sont couvertes par les tests.
- Résultat : 316 672 or, 730 999 élixir et 16 130 élixir noir comptabilisés, bonus inclus, puis retour au village. Deux images du montant court d’élixir noir reproduisent les variations du décor dans `testdata`.
- Interface moderne : les quatre cases du panneau Cycle tiennent dans la taille minimale 1040 × 860 ; panneau mesuré à 314 × 195, dernière case à 167 pixels.

Ces validations portent sur les captures et la composition testées, sur l’interface française 1920 × 1080. Une lecture ambiguë bloque les dépenses ; le bot ne remplace pas une recommandation illisible par un choix arbitraire.


## Commandes indépendantes et reprise

L’onglet **Actions** permet de lancer seulement les bâtiments, les remparts ou une attaque unique. Les réglages du cycle ne sont pas modifiés par ces actions ; les boutons sont verrouillés pendant une opération. Le bouton **Cycle complet** utilise les options automatiques du panneau Cycle.

Sur le message Google Play Jeux **Connexion perdue**, le bot clique sur **Réessayer**, attend un écran de jeu confirmé puis reprend l’action depuis un état relu. Il ne répète pas le clic interrompu. **Arrêter** interrompt aussi les tentatives de reconnexion.

Un résultat de combat illisible est archivé avec son identifiant dans `%USERPROFILE%\CoCFarmBot\unread-results` avant la reprise du cycle. Ses gains ne sont pas inventés ni ajoutés aux statistiques. Les réserves et les confirmations de dépenses, elles, doivent toujours être lisibles pour autoriser un achat.
