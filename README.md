# CoC Farm Bot v2.0.0

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

La version v2.0.0 conserve les données déjà créées par la génération de stockage précédente.

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