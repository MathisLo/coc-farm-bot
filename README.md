# CoC Farm Bot v2.0.17

## Améliorations de bâtiments du 4 octobre 2026 (v2.0.17)

Les variantes OCR de « Bombe géante » et les lignes brièvement illisibles ne bloquent plus la sélection. Les prix de la liste sont recoupés sur plusieurs zones pour éviter de lire 200 000 à la place de 3 200 000. Après contrôle des ouvriers et des réserves, une amélioration directe est retrouvée dans la liste même si celle-ci revient en haut. Le prix du bouton vert est vérifié sur deux zones distinctes avant tout paiement.

Un essai direct sur la fenêtre Clash 1920 x 1080 a confirmé l'amélioration de la Catapulte explosive pour 6 000 000 d'élixir : 6 130 441 avant, 130 441 après, et 4 puis 3 ouvriers libres. Les lectures non confirmées continuent de bloquer la dépense.

## Corrections du 4 octobre 2026 (v2.0.16)

Le bot ne plante plus si plusieurs lectures OCR des réserves se contredisent. Sur la fenêtre `Clash of Clans - TCDVeNom` en 1920 x 1080, il relit l'élixir sans perdre les premiers chiffres et reconnaît les cartes de paiement même si l'OCR dédouble un libellé. Un essai en jeu a confirmé deux remparts à 4 000 000 d'élixir chacun : 10 799 873 avant, 2 799 873 après. Le paiement reste interdit si les réserves ou le coût ne sont pas confirmés.

La lecture du résultat a été ajustée pour les montants coupés et les bonus de victoire. La capture du combat signalé donne 630 243 or, 853 111 élixir et 10 207 élixir noir, bonus inclus. Une nouvelle attaque en jeu a confirmé la pose de 10 électro-dragons, 1 dragon, 4 héros et 5 Rage, puis la comptabilisation du butin et le retour au village.

## Validation de l'attaque (v2.0.15)

Le nombre d'électro-dragons, de dragons, de héros (0 à 4) et de sorts Rage (0 à 5) se règle dans l'onglet **Armée**. Le bot repère les cartes des troupes et le sort Rage dans la barre de combat même lorsque leur ordre change. Si le badge des héros ou celui des sorts est illisible sur l'écran de préparation, il recoupe la lecture avec les cartes visibles avant de lancer la recherche.

Le 3 octobre 2026, l'EXE v2.0.15 a effectué une attaque unique sur la fenêtre `Clash of Clans - TCDVeNom` en 1920 x 1080 : 8 électro-dragons, 1 dragon, 3 héros et 5 Rage confirmés, puis retour au village et comptabilisation du butin. Les 291 tests automatisés et l'autotest de l'EXE ont aussi réussi. La capture du diagnostic `BodaciousHermit19914` confirme en rejeu headless 2 cartes de héros et 5 Rage ; ce compte distinct n'a pas été testé en direct.

Pour reproduire une seule attaque avec l'EXE et produire un rapport JSON, utiliser `CoCFarmBot.exe --live-attack-report rapport.json`. Cette commande agit dans la fenêtre Clash sélectionnée et utilise la composition déjà enregistrée ; elle désactive les améliorations et l'enchaînement des attaques pour cette validation.

## Composition d'attaque (v2.0.14)

L'onglet **Armée** règle désormais le nombre de héros à déployer (0 à 4) en plus des troupes et des sorts Rage. Le bot attend les héros demandés avant de chercher une attaque. La pose de Rage reste tentée même si la disposition des héros est momentanément illisible ; si la carte Rage demandée ne peut pas être reconnue, le diagnostic signale une erreur explicite plutôt que de déclarer la pose réussie.

## Composition d’attaque configurable (v2.0.13)

L’onglet **Armée** permet de choisir les nombres d’électro-dragons, de dragons et de sorts Rage. Les valeurs sont sauvegardées et limitées lors du déploiement. Le contrôle avant recherche vérifie aussi le nombre de Rage demandé et les places de sort nécessaires.

## Diagnostic complet (v2.0.12)

Dans le lanceur, ouvrir **Outils** ou **Journal**, puis cliquer sur **Exporter le diagnostic**. Enregistrer le ZIP et le joindre seul au signalement du problème. Il contient les journaux récents et complets, les captures disponibles, les réglages enregistrés et affichés, l'état de la fenêtre du jeu, les contrôles OCR, la version et l'empreinte de l'EXE. Une panne au démarrage affiche un écran de secours avec le même export.

Le ZIP peut contenir le nom du compte, des captures du jeu et des chemins locaux : le transmettre uniquement à la personne chargée du dépannage. L'export n'envoie rien automatiquement.

Validation du 26 septembre 2026 sur PC-FIXE : 284 tests passent et un ZIP créé à partir des données du bot a été ouvert et contrôlé. Cette vérification du diagnostic est distincte des essais en jeu sur TCD_VeNom.

## Remparts sur PC-FIXE (v2.0.12)

Le diagnostic du 26 septembre montrait que la ligne « Rempart x193 » changeait de position dans la liste et que l'OCR lisait parfois « Rémparb » ou « Re•mpahb ». Après correction de ces lectures, le panneau « Améliorer plus » est distingué du panneau de groupe, et la lecture des réserves en 1920 x 1080 conserve le premier chiffre. Un essai direct sur PC-FIXE a confirmé l'amélioration d'un rempart à 4 000 000 d'or : 6 886 995 avant, 2 886 995 après. La fenêtre de jeu portait le titre « Clash of Clans - TCDVeNom » ; cet essai a eu lieu sur PC-FIXE, et ne doit pas être confondu avec les anciens essais sur la VM TCD_VeNom.

Les 287 tests automatisés passent après ce correctif.

## Validation du 24 septembre 2026 (v2.0.8)

Sur TCD_VeNom, dans la fenêtre de jeu 1323 x 744, le bot a lancé une Tour d'archères à 4 000 000 d'or puis un Éradicateur de héros à 6 000 000 d'élixir (durée affichée : 9 h 59), en passant de trois à un ouvrier libre. Il a également acheté un rempart unique (`x1`) en or et un autre en élixir, à 4 000 000 chacun. Un nouvel essai a confirmé un rempart isolé en or après correction d'une lecture initiale à 400 000, et un cycle suivant a payé un autre rempart en élixir. Les journaux de ces essais sont conservés dans `%USERPROFILE%\CoCFarmBot\runs`. Plusieurs essais intermédiaires ont été interrompus par une mauvaise lecture OCR du premier million restant ; leurs captures alimentent les tests de régression.

Un cycle de 31,9 minutes sur TCD_VeNom a confirmé 6 attaques complètes (10 électro-dragons, 1 dragon, 5 Rage, 4 héros et 40 troupes temporaires à chaque fois), 5 collectes de foreuses d'élixir noir et 3 paiements de remparts. Il s'est arrêté normalement au village. Le bot ne cherche les troupes temporaires que lorsque leur carte rouge apparaît dans la barre de combat ; il cesse automatiquement de le faire quand elle disparaît après l'événement. La recherche des bâtiments s'arrête plus tôt quand le menu est immobile, et une alerte indique si l'option d'amélioration des bâtiments est désactivée. Les lectures critiques et le panneau compact d'amélioration sont testés sur captures en 1387 x 780, 1920 x 1080 et 2560 x 1440 ; ces trois résolutions ne sont pas toutes validées en jeu. La reconnexion reste limitée aux dialogues reconnus (Réessayer / Recharger le jeu).

## Validation du 24 septembre 2026 (v2.0.7)

Sur TCD_VeNom, dans une fenêtre de jeu 1323 x 744, un cycle de 34,5 minutes a confirmé trois attaques complètes (10 électro-dragons, 1 dragon, 4 héros et 5 Rage à chaque fois), la collecte répétée des foreuses d'élixir noir, une tour d'archers lancée pour 4 000 000 d'or et un rempart amélioré pour 4 000 000 d'élixir avec une réserve supérieure à 1 000 000. Le scan des bâtiments passe avant celui des remparts et s'arrête après deux propositions instables pour ne pas bloquer les attaques. Il restait deux ouvriers libres à la fin de cet essai : le passage à un seul ouvrier n'a pas été démontré en jeu, faute d'une autre proposition payable et lisible.

La ligne d'un rempart unique (`x1`) a été reconnue, mais elle coûtait 4 000 000 et n'était pas payable avec la réserve exigée au moment du test. Les lectures critiques ont aussi été testées sur des captures en 1920 x 1080, 2560 x 1440 et 1387 x 780 ; ces tailles n'ont pas toutes été validées en jeu. Les messages de reconnexion reconnus sont couverts par les tests, sans garantie pour un message inconnu.

## Validation du 23 septembre 2026

Sur TCD_VeNom, dans une fenêtre de jeu 1765 x 993, une attaque complète a confirmé séparément 8 électro-dragons, 1 dragon, 5 sorts Rage et 4 héros, puis le retour au village et la comptabilisation du butin. Les cartes des deux troupes ont été localisées dans la barre d'armée même lorsque leur ordre différait des positions par défaut. Les Rage ont été posés vers les points de déploiement des troupes. Un rempart a aussi été amélioré seul pour 4 000 000 d'élixir, avec confirmation de l'achat. Les journaux détaillés de ces essais restent dans `%USERPROFILE%\CoCFarmBot\runs`.

Le bot reconnaît les boutons **Réessayer** et **Recharger le jeu** sur les dialogues de reconnexion connus et attend un écran stable avant de reprendre. Un message inconnu ou sans commande de reconnexion reconnue reste un arrêt prudent, pas une promesse de reprise universelle.

Application Windows pour Google Play Jeux PC. Elle lit le butin des bases adverses, cherche une base qui atteint les seuils configurÃ©s, puis dÃ©ploie lâ€™armÃ©e choisie. Les commandes sont envoyÃ©es Ã  la fenÃªtre du jeu sans dÃ©placer la souris Windows.

**Au village :** le bot parcourt la liste des ouvriers, lance chaque fois le bÃ¢timent payable le plus cher et s'arrÃªte quand il ne reste qu'un ouvrier libre. Il exclut toujours l'HÃ´tel de ville. Il utilise ensuite l'or et l'Ã©lixir restants pour les remparts, en conservant au moins un million de chaque ressource.

## DÃ©marrer

TÃ©lÃ©charger puis lancer [CoCFarmBot.exe depuis la derniÃ¨re Release GitHub](https://github.com/MathisLo/coc-farm-bot/releases/latest/download/CoCFarmBot.exe) ou, depuis le dossier du projet :

```powershell
.\.venv\Scripts\python.exe main.py
```

Dans lâ€™application :

1. Choisir la fenÃªtre Clash of Clans. Le bouton **â†»** actualise la liste ; **Lire lâ€™Ã©cran** affiche une capture et les ressources lues.
2. RÃ©gler les seuils dâ€™or et dâ€™Ã©lixir, la marge, les nombres de troupes prÃ©vus et les options du cycle.
3. Cliquer sur **Enregistrer** pour garder ces rÃ©glages, ou sur **Lancer le cycle** pour les enregistrer et dÃ©marrer.
4. **ArrÃªter** interrompt la boucle. Les Ã©vÃ©nements sont affichÃ©s dans le journal.

La **simulation** clique rÃ©ellement pour rechercher et passer les bases, mais ne dÃ©ploie pas de troupes et nâ€™amÃ©liore pas de remparts. En mode rÃ©el, le bot lit le nombre de troupes prÃ©sentes dans la barre de combat, les rÃ©partit sur une seule ligne en haut Ã  gauche et envoie les hÃ©ros sur cette mÃªme ligne juste derriÃ¨re. Les troupes sont posÃ©es par groupes de trois maximum, Ã  60 ms dâ€™intervalle hors capture et clics. Deux lectures concordantes du compteur vÃ©rifient chaque groupe avant de continuer. Un rÃ©sultat illisible ou incohÃ©rent arrÃªte la pose ; un simple changement de pixels nâ€™est pas une confirmation. Les nombres saisis dans lâ€™interface servent de prÃ©vision ; toutes les unitÃ©s disponibles des deux types pris en charge sont envoyÃ©es. La pose des trois hÃ©ros est Ã©galement vÃ©rifiÃ©e visuellement.

**ArrÃªter** bloque les nouveaux clics de toutes les actions, y compris les hÃ©ros et les confirmations de remparts. Un clic dÃ©jÃ  envoyÃ© est relÃ¢chÃ©. Les lectures OCR sont annulables et limitÃ©es Ã  huit secondes par appel ; une base dont lâ€™Ã©cran ou le butin reste illisible dispose dâ€™un budget de 35 secondes. Ensuite, sa capture est conservÃ©e dans `%USERPROFILE%\CoCFarmBot\unread-enemies` et le bot passe Ã  la suivante uniquement si le bouton Suivant est reconnu sur une nouvelle capture. Sinon, il sâ€™arrÃªte sans clic. Avec le rÃ©glage Â« or ou Ã©lixir Â», une seule ressource lisible atteignant son seuil suffit ; le rÃ©glage exigeant les deux ressources conserve ses deux vÃ©rifications. **Lire lâ€™Ã©cran** et **Relever le profil** travaillent en arriÃ¨re-plan : lâ€™interface et le bouton ArrÃªter restent disponibles. Une seule opÃ©ration est autorisÃ©e Ã  la fois, et les rÃ©glages utilisÃ©s ne changent pas en cours de cycle.

## Adapter les positions

Dans l’onglet **Armée**, configurez séparément les quantités d’électro-dragons, de dragons et de sorts Rage. Les valeurs sont enregistrées avec les réglages et le bot limite le déploiement à ces quantités. Les sorts Rage peuvent être réglés de 0 à 5 ; chacun occupe deux places. La composition doit être présente dans les camps avant la recherche, sinon le journal indique les quantités attendues.

Les lectures critiques sont testées sur des captures redimensionnées en 1920 x 1080, 2560 x 1440 et 1387 x 780. Pour une autre largeur, y compris un 780p non 16:9, régler d'abord la fenêtre du jeu à la taille voulue, puis ouvrir **Calibrer les positions...** : la taille intérieure affichée est celle de la capture et son format est enregistré avec les positions. Le bot refuse les clics si le format de la fenêtre ne correspond plus au calibrage. Ces tests sur images ne remplacent pas un essai réel sur le PC concerné.

Le profil fourni vise lâ€™interface franÃ§aise en **16:9**, avec dragons, Ã©lectro-dragons et trois hÃ©ros. Les captures et les clics utilisent la zone intÃ©rieure de la fenÃªtre, sans barre de titre. Les dimensions sont relues Ã  chaque capture et chaque clic. Un redimensionnement entre la lecture et lâ€™action interrompt le bot ; relancer une fois la fenÃªtre stabilisÃ©e. Si son format diffÃ¨re du calibrage, aucun clic nâ€™est envoyÃ©.

Le bouton **Calibrer les positionsâ€¦** permet dâ€™adapter les boutons, les zones de lecture, les cartes de troupes, les hÃ©ros et les seize points de dÃ©ploiement :

1. Afficher le menu concernÃ© dans le jeu, puis ouvrir le calibrage.
2. Choisir lâ€™Ã©lÃ©ment dans la liste. Cliquer sur lâ€™aperÃ§u pour placer un point ; tracer un rectangle pour dÃ©finir une zone de lecture.
3. Utiliser **Actualiser la capture** aprÃ¨s avoir changÃ© de menu, ou **Charger une captureâ€¦** pour une image enregistrÃ©e au mÃªme format.
4. Enregistrer. Les positions et le format sont conservÃ©s avec les autres rÃ©glages. **RÃ©initialiser cet Ã©lÃ©ment** restaure sa position dâ€™origine.

Les clics dans lâ€™aperÃ§u ne commandent jamais le jeu. Pour dÃ©placer une troupe, ajuster sa sÃ©lection, son compteur et son icÃ´ne. Pour un hÃ©ros, ajuster sa sÃ©lection, son icÃ´ne et sa barre de vie. Les rÃ©glages individuels sont utilisÃ©s tels quels ; les hÃ©ros non personnalisÃ©s conservent le dÃ©calage automatique liÃ© Ã  lâ€™engin de siÃ¨ge. Il ne sâ€™agit pas dâ€™une reconnaissance automatique de toute composition dâ€™armÃ©e ou de toute interface.

Lâ€™option du cycle amÃ©liore les remparts entre les attaques. Le bouton **AmÃ©liorer les remparts** lance cette action seule. Le bot parcourt la liste des ouvriers, repÃ¨re les lignes Â« Rempart Â» visibles et essaie un autre groupe si le premier dÃ©passe les rÃ©serves. Il utilise **AmÃ©liorer plus** pour former le plus grand lot payable et conserve au moins 1 000 000 dâ€™or et 1 000 000 dâ€™Ã©lixir avant chaque dÃ©pense. Comme les coÃ»ts sont par paliers, il peut rester un peu plus dâ€™un million si une autre amÃ©lioration ferait passer sous ce seuil. Si les montants, lâ€™Ã©cran ou la confirmation sont illisibles, il sâ€™arrÃªte sans confirmer la dÃ©pense.

Les commandes de jeu nÃ©cessitent une fenÃªtre Clash accessible. Si le jeu change de menu pendant une action, arrÃªtez le bot et revenez au village avant de relancer les remparts.

## Construire lâ€™exÃ©cutable

```powershell
.\BUILD.ps1
```

Le rÃ©sultat est `dist\CoCFarmBot.exe`. Le script exÃ©cute les tests, construit dans `build\release`, puis lance un autotest de lâ€™exÃ©cutable sur une image synthÃ©tique, sans ouvrir le bot ni agir dans le jeu. Il vÃ©rifie les empreintes des sources embarquÃ©es avant de remplacer lâ€™ancien exÃ©cutable. `dist\release-check.json` conserve le rÃ©sultat et `dist\build-manifest.json` contient les empreintes des sources et de lâ€™exÃ©cutable.

La refonte charge les ressources officielles depuis `assets/kit/` et les styles et animations du kit depuis `ui/kit/`. PyInstaller intÃ¨gre ces fichiers, lâ€™icÃ´ne multirÃ©solution `assets/kit/app/app.ico` et les mÃ©tadonnÃ©es Windows gÃ©nÃ©rÃ©es depuis `app_meta.py`. La version affichÃ©e par lâ€™interface et celle de lâ€™exÃ©cutable partagent cette mÃªme source.

Si les dÃ©pendances sont dÃ©jÃ  installÃ©es : `./BUILD.ps1 -SkipDependencyInstall`. Un Ã©chec dâ€™installation, de test ou de construction interrompt le script. Fermer lâ€™ancienne application avant de remplacer son exÃ©cutable.

## VÃ©rifier sans agir dans le jeu

```powershell
.\.venv\Scripts\python.exe -B -m unittest -v test_main test_regressions test_windows_integration
```

Les tests couvrent lâ€™arrÃªt avant les clics, les dimensions et changements de fenÃªtre, les compteurs, les dÃ©lais OCR, le calibrage et la rÃ©activitÃ© de lâ€™interface. `testdata` contient les extraits rÃ©els reproduisant les erreurs de rÃ©serves, le compteur sÃ©lectionnÃ© Â« x1 Â» et le dÃ©calage des boutons lorsque des anneaux de rempart sont disponibles. Les tests Windows utilisent ces images et des fenÃªtres de test, sans agir dans le jeu.

La vÃ©rification rÃ©elle du 19 septembre 2026 a confirmÃ© un dÃ©ploiement de 8 Ã©lectro-dragons, 1 dragon et 3 hÃ©ros, suivi du retour au village, puis 13 amÃ©liorations de remparts dans un cycle. Un dernier essai a confirmÃ© une amÃ©lioration supplÃ©mentaire, puis lâ€™arrÃªt faute de budget : 1 045 191 or et 1 429 534 Ã©lixir conservÃ©s. Ce relevÃ© dÃ©crit ces tests sur lâ€™interface franÃ§aise 1920Ã—1080, pas une garantie pour toute composition ou interface.

Les chiffres blancs sont isolÃ©s des fonds colorÃ©s pour lâ€™OCR. Le compteur Â« x1 Â», parfois ignorÃ© par Windows, dispose aussi dâ€™une reconnaissance des deux caractÃ¨res. Avant chaque attaque retenue en mode rÃ©el, le bot dÃ©zoome avec la molette, puis reprend une capture avant de poser les troupes. Les points de pose refusÃ©s sont Ã©cartÃ©s pour le reste du dÃ©ploiement de cette troupe. Les boutons Ajouter et les paiements en or/Ã©lixir sont dÃ©tectÃ©s sur chaque nouvelle capture. Chaque ajout est confirmÃ© par le prix du groupe avant le clic suivant, mÃªme lorsque le bouton +10 disparaÃ®t et dÃ©place la rangÃ©e. Les anneaux ne sont jamais sÃ©lectionnÃ©s. Le dernier rempart utilise sa confirmation individuelle. Une ligne de menu doit prÃ©senter son Ã©tiquette verte et son libellÃ© : un nom visible derriÃ¨re le menu transparent ne suffit pas.

Pendant lâ€™Ã©vÃ©nement, le bot attend lâ€™apparition des trois cartes puis choisit **lâ€™or ou lâ€™Ã©lixir en prioritÃ©** puis les **tickets dâ€™Ã©vÃ©nement** si aucune ressource nâ€™est reconnue. **Aucune troupe dâ€™Ã©vÃ©nement nâ€™est sÃ©lectionnÃ©e** ; une carte illisible ne dÃ©clenche aucun clic. Il confirme la fermeture de la fenÃªtre avant de reprendre les autres commandes. Cette surveillance continue aprÃ¨s le dÃ©ploiement, jusquâ€™au retour au village. Une fenÃªtre persistante provoque un arrÃªt. Les commandes de dÃ©zoom et de rÃ©compense respectent le bouton **ArrÃªter**.

La reconnaissance des hÃ©ros exige une barre de vie verte horizontale sous un bord sombre : lâ€™herbe derriÃ¨re une carte non dÃ©ployÃ©e ne suffit plus Ã  considÃ©rer le hÃ©ros comme posÃ©. Le test rÃ©el a reproduit le faux positif sur la reine, puis confirmÃ© la pose des trois hÃ©ros aprÃ¨s correction. Le dÃ©zoom a Ã©tÃ© vÃ©rifiÃ© depuis une vue fortement agrandie ; les choix automatiques ont Ã©tÃ© vÃ©rifiÃ©s sur des cartes dâ€™or et dâ€™Ã©lixir.

## Fichiers utiles

- `main.py` : logique du bot, contrÃ´leur de l'application et points d'entrÃ©e.
- `modern_dashboard.py`, `web_dashboard.html`, `ui/` : fenÃªtre WebView2 et interface inspirÃ©e de la maquette fournie ; le moteur Python reste dans `main.py`.
- `assets/kit/` : identitÃ©, icÃ´nes, ressources et fragments dÃ©coratifs issus du kit fourni.
- `app_meta.py` : nom et version de lâ€™application utilisÃ©s par lâ€™interface et le build.
- `dashboard.py`, `dashboard_layout.py` : interface Tkinter conservÃ©e pour les composants internes et le calibrage.
- `ui_theme.py`, `ui_widgets.py` : couleurs, styles et composants visuels rÃ©utilisables.
- `calibration.py` : Ã©dition des positions sur une capture.
- `test_main.py`, `test_regressions.py`, `test_storage.py`, `test_windows_integration.py` : validations locales.
- `requirements.txt` : dÃ©pendances Python.
- `BUILD.ps1` : crÃ©ation de lâ€™exÃ©cutable Windows.
- `%USERPROFILE%\CoCFarmBot\config-v2.json` : rÃ©glages personnels de la version en cours.
- `%USERPROFILE%\CoCFarmBot\bot.log` : journal dÃ©taillÃ©.
- `%USERPROFILE%\CoCFarmBot\runs\` : un journal distinct pour chaque action lancÃ©e ; une capture `.png` du dernier Ã©cran est ajoutÃ©e si l'action Ã©choue.
- `%USERPROFILE%\CoCFarmBot\account_snapshot.json` : dernier relevÃ© demandÃ© via **Relever le profil**.

Dans l'onglet **Journal**, cliquez sur **Exporter le diagnostic**, puis joignez ce ZIP Ã  votre message en cas de blocage. Le bouton reste disponible pendant un cycle. Chaque action a son propre fichier avec ses rÃ©glages, toutes les demandes et rÃ©ponses OCR, les captures demandÃ©es, les clics et dÃ©filements, les choix et refus de dÃ©pense, les rÃ©serves, les ouvriers, les attentes et les erreurs complÃ¨tes. En cas d'erreur, le ZIP inclut aussi le dernier Ã©cran capturÃ©. Si une rÃ©compense finale est illisible, le ZIP contient Ã©galement cet Ã©cran. Un export pendant l'action est une copie Ã  cet instant ; exportez de nouveau aprÃ¨s l'arrÃªt pour obtenir la fin du journal.

La version v2.0.5 conserve les données déjà créées par la génération de stockage précédente.

Le suivi des fonctionnalitÃ©s et des validations se trouve dans [Notion](https://app.notion.com/p/3dccca7fe8b78060a5c3ca2aa4b73fa8). Le dÃ©pÃ´t GitHub contient les sources et chaque mise Ã  jour publiÃ©e fournit un exÃ©cutable Windows testÃ© dans les Releases. Les fichiers de construction et les captures de diagnostic restent locaux.
# Statistiques de rÃ©colte

La console affiche les trois ressources en haut, les rÃ©glages Butin, ArmÃ©e et Cycle Ã  gauche, puis le journal, l'aperÃ§u et les actions ponctuelles Ã  droite. Les commandes Enregistrer, Remparts, Lancer le cycle et ArrÃªter restent visibles en bas. Taille minimale : 1080 Ã— 710. La fenÃªtre initiale se place dans l'espace de travail Windows, au-dessus de la barre des tÃ¢ches.

L'application affiche les cumuls d'or, d'Ã©lixir et d'Ã©lixir noir ainsi que le nombre de combats comptabilisÃ©s. Le suivi commence avec cette version : les anciennes rÃ©coltes ne sont pas reconstituÃ©es.

Les gains sont lus sur le rÃ©sultat final du combat, avec le bonus de ligue. Les rÃ©compenses d'Ã©vÃ©nement dÃ©jÃ  incluses dans ce rÃ©sultat ne sont pas ajoutÃ©es une seconde fois. Les dÃ©penses de remparts ne soustraient rien Ã  ces cumuls. Il s'agit du butin annoncÃ© par le jeu, qui peut dÃ©passer la place restante dans les rÃ©serves.

Les totaux sont sauvegardÃ©s dans `%USERPROFILE%\CoCFarmBot\farm-stats.json` et restaurÃ©s au lancement. MÃªme en mode attaque unique, le bot attend le rÃ©sultat pour le comptabiliser. Si la lecture reste incertaine, le rÃ©sultat est conservÃ© dans `unread-results` sans ajouter de gains aux totaux, puis le cycle reprend. Un rÃ©sultat dÃ©jÃ  enregistrÃ© n'est pas recomptÃ©. Un combat quittÃ© manuellement avant sa lecture ne peut pas Ãªtre reconstituÃ©.


Les amÃ©liorations de bÃ¢timents utilisent les ressources disponibles sans imposer le plancher d'un million rÃ©servÃ© aux remparts. Le bot lit toute la liste, confirme deux fois le prix et la ressource, puis sÃ©lectionne le bÃ¢timent payable le plus cher. Il relit l'Ã©cran de confirmation et les ouvriers avant l'achat. L'HÃ´tel de ville est exclu, mÃªme si son prix est le plus Ã©levÃ©. Les remparts automatiques commencent lorsque exactement un ouvrier reste libre ; ils conservent au moins un million d'or et d'Ã©lixir.

Si aucun rempart n'est payable avec cette rÃ©serve, le bot termine la recherche des remparts et poursuit le cycle vers l'attaque.

## Validation rÃ©elle du 20 septembre 2026

Sur le village franÃ§ais en 1920 Ã— 1080, le bot a lancÃ© l'Aigle artilleur (3 600 000 or), la Catapulte explosive (3 200 000 Ã©lixir) et la Bougie incandescente (3 200 000 or). Le nombre d'ouvriers libres est passÃ© de 4 Ã  1. Il a ensuite amÃ©liorÃ© 11 remparts, dÃ©pensÃ© 5 400 000 Ã©lixir et 1 200 000 or, puis s'est arrÃªtÃ© avec 1 479 253 or et 1 400 000 Ã©lixir. Ces montants ont Ã©tÃ© relus dans le jeu aprÃ¨s les achats.


## Validation des corrections du 19 septembre 2026

Les essais rÃ©els ont utilisÃ© la capture et les messages de fenÃªtre en arriÃ¨re-plan, sans activer le jeu ni dÃ©placer la souris. Le jeu doit rester lancÃ© et capable de produire ses images.

- Remparts : 17 amÃ©liorations consÃ©cutives, puis arrÃªt avec 1 428 809 or et 1 497 947 Ã©lixir (`diagnostics/upgrades_no_hdv.png`).
- AmÃ©lioration conseillÃ©e : piÃ¨ge Ã  ressort Ã  500 000 or, compteur vÃ©rifiÃ© de 4 Ã  3 ouvriers libres ; rÃ©serves finales de 1 348 627 or et 2 333 092 Ã©lixir (`diagnostics/spring_verified_end.png`). Le HDV est exclu de la sÃ©lection et bloquÃ© Ã  la confirmation. Le dernier ouvrier est protÃ©gÃ© par les tests du parcours dâ€™amÃ©lioration et du contrÃ´le de budget.
- Combat : 8 Ã©lectro-dragons, 1 dragon et 3 hÃ©ros confirmÃ©s automatiquement ; carte de 289 429 Ã©lixir choisie devant deux troupes dâ€™Ã©vÃ©nement (`diagnostics/strict_event_cycle.log`, `diagnostics/strict_event_card_2.png`). La prioritÃ© des tickets en lâ€™absence de ressource et lâ€™absence de repli sur une troupe sont couvertes par les tests.
- RÃ©sultat : 316 672 or, 730 999 Ã©lixir et 16 130 Ã©lixir noir comptabilisÃ©s, bonus inclus, puis retour au village. Deux images du montant court dâ€™Ã©lixir noir reproduisent les variations du dÃ©cor dans `testdata`.
- Interface : les commandes et les quatre options du panneau Cycle ont Ã©tÃ© vÃ©rifiÃ©es Ã  la taille minimale 1080 Ã— 760.

Ces validations portent sur les captures et la composition testÃ©es, sur lâ€™interface franÃ§aise 1920 Ã— 1080. Une lecture ambiguÃ« bloque les dÃ©penses ; le bot ne remplace pas une recommandation illisible par un choix arbitraire.


## Commandes indÃ©pendantes et reprise

Lâ€™onglet **Actions** permet de lancer seulement les bÃ¢timents, les remparts ou une attaque unique. Les rÃ©glages du cycle ne sont pas modifiÃ©s par ces actions ; les boutons sont verrouillÃ©s pendant une opÃ©ration. Le bouton **Lancer le cycle** utilise les options automatiques du panneau Cycle.

Sur le message Google Play Jeux **Connexion perdue**, le bot clique sur **RÃ©essayer**, attend un Ã©cran de jeu confirmÃ© puis reprend lâ€™action depuis un Ã©tat relu. Il ne rÃ©pÃ¨te pas le clic interrompu. **ArrÃªter** interrompt aussi les tentatives de reconnexion.

Au village, le bot collecte les bulles dâ€™or et dâ€™Ã©lixir reconnues sur les mines et extracteurs avant de lancer les autres actions. Il vÃ©rifie que chaque bulle disparaÃ®t aprÃ¨s le clic et reporte la collecte si un menu couvre le village. Le message dâ€™inactivitÃ© **DÃ©connexion suite Ã  une pÃ©riode dâ€™inactivitÃ©** dÃ©clenche **Recharger le jeu** ; le bot attend ensuite deux captures concordantes avant de reprendre le cycle.

Un rÃ©sultat de combat illisible est archivÃ© avec son identifiant dans `%USERPROFILE%\CoCFarmBot\unread-results` avant la reprise du cycle. Ses gains ne sont pas inventÃ©s ni ajoutÃ©s aux statistiques. Les rÃ©serves et les confirmations de dÃ©penses, elles, doivent toujours Ãªtre lisibles pour autoriser un achat.`n
