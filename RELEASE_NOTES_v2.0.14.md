# CoC Farm Bot 2.0.14

- Ajout du réglage du nombre de héros à déployer (0 à 4), avec attente de leur disponibilité avant la recherche.
- Le déploiement des sorts Rage ne dépend plus de la détection préalable de la disposition des héros.
- Une carte Rage demandée mais non détectée produit maintenant une erreur explicite au lieu d'un faux succès silencieux.
- Conservation automatique des anciens réglages : les anciens comptes avec héros activés migrent vers 4 héros, ceux désactivés vers 0.
- Validation complète : tests automatisés et autotest de l'exécutable.
