# CoC Farm Bot v2.0.19

- Corrige l’arrêt « Écran attendu absent après : Ouverture du menu Attaquer » : la liste des ouvriers laissée ouverte après une tentative de remparts est fermée, puis le village est confirmé sur deux captures avant le clic d’attaque.
- Corrige la lecture de l’or tronquée lorsque l’OCR sépare les chiffres d’un même groupe. Le diagnostic affichait 2 719 974 or, mais le bot retenait 719 974.
- Reconnaît la variante OCR « hmbe géante » dans le panneau de la Bombe géante. Les contrôles de titre, coût et ressource avant paiement restent actifs.
- Corrige les bonus de victoire tronqués en 1920 × 1080 : deux zones plus larges du texte doivent donner le même montant avant de remplacer une lecture trop petite.

Les captures du diagnostic servent de tests de régression. Les réserves illisibles ou les prix non confirmés continuent d’interdire une dépense.

Validation : 314 tests automatisés et autotest de l’EXE réussis. Le fichier final a été testé en jeu sur PC-FIXE en 1920 × 1080, avec la liste des ouvriers ouverte au départ : fermeture confirmée, déploiement de 10 électro-dragons, 1 dragon, 4 héros et 5 Rage, puis retour au village. Les statistiques ont augmenté exactement de 2 229 474 or, 2 988 573 élixir et 15 573 élixir noir, correspondant au résultat affiché, bonus inclus. La correction de la Bombe géante est vérifiée sur sa capture ; aucun bâtiment n’a été acheté pendant ces essais.
