# CoC Farm Bot v2.0.9-rc1 - validation PC

Cette version d'essai cible deux problèmes observés dans les diagnostics PC du 24 septembre, en 1920 x 1080. Elle ne remplace pas encore la v2.0.8 stable : un nouvel essai sur le PC est nécessaire.

## Ce que montrent les journaux PC

- L'EXE lancé avait bien le SHA-256 de la v2.0.8. Après 10 électro-dragons, 1 dragon, 5 Rage et 4 héros, le combat continuait, mais aucune recherche des 40 troupes d'événement n'a abouti. Le filtre fondé sur la couleur rouge pouvait ignorer une carte rendue différemment sur le PC.
- Avec 2 ouvriers libres et des ressources suffisantes, le bot a identifié une Caserne noire à 2,88 M d'élixir. La liste des ouvriers a bougé avant le clic ; il a refusé de sélectionner la ligne et a recommencé un balayage complet. Le second ZIP s'arrête pendant ce balayage et ne prouve pas son issue finale.

## Modifications

- La recherche des renforts examine les emplacements de troupes et peut reconnaître une carte neuve `x40` par son compteur même si son icône n'est pas rouge. Après chaque lot de cinq clics, le compteur doit baisser ; le dernier lot doit être confirmé à `x0`. Aucun clic supplémentaire n'est envoyé si cette confirmation échoue.
- Quand aucune carte `x40` n'est reconnue, le bot enregistre automatiquement une image de la barre de combat. Le prochain ZIP de diagnostic inclura cette image, ce qui permettra de voir sa position et son apparence réelles sans capture manuelle.
- Avant une amélioration de bâtiment, le bot retrouve la ligne par son nom, son prix et sa ressource sur deux captures stables, puis clique à sa position actuelle. Une ligne encore ambiguë reste refusée sans dépense. La priorité au bâtiment payable le plus cher et la réservation d'un ouvrier sont conservées.
- Chaque nouveau journal d'action indique désormais la version de l'application en plus du chemin de l'EXE.

## Vérification

- Des tests reproduisent une carte `x40` dont l'icône rouge est absente sur une capture redimensionnée à 1920 x 1080, l'export de la barre dans le ZIP et une ligne de bâtiment déplacée avant le clic.
- Suite complète : 256 tests exécutés, 1 ignoré, aucun échec. L'EXE construit a passé son auto-test de version et de sources.
- SHA-256 de `CoCFarmBot.exe` : `1e7b0b9e9c252135b2c220912e257ef818760c2f282ccb138a7a2f333fc05ea6`.
- **Non confirmé sur le PC à ce stade.** Pour valider ce correctif, lancer cet EXE sur le PC puis exporter un ZIP de diagnostic après une attaque et une tentative d'amélioration longue.
