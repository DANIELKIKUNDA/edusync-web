# Périmètres opérationnels — audit et premier lot

## Règle
Une permission et son périmètre forment une seule autorisation. Un droit SCHOOL d’un autre module ne doit jamais élargir une consultation SECTION ou CLASS. Plusieurs sections explicitement accordées sont réunies. Sans périmètre effectif, le nouveau sélecteur ne renvoie rien. Les paramètres d’administration de la structure restent distincts des filtres opérationnels.

## Constats et corrections de ce lot
- Résolution commune des classes : un périmètre vide était assimilé à toute l’école. Il échoue désormais de façon fermée, conformément aux vues mensuelles et au personnel. Les tests historiques qui codifiaient l’ancien élargissement sont rectifiés.
- Effectifs : les boutons école/maternelle/primaire/secondaire étaient codés en dur. Leurs choix viennent désormais du serveur pour la capacité de l’onglet consulté. Une seule section est présélectionnée ; une vue école demande un droit SCHOOL explicite.
- Élèves : la liste des classes était demandée sans capacité, et les options provenaient d’un sélecteur non filtré. Les consultations demandent maintenant le périmètre de lecture des élèves. Une seule section est sélectionnée sans choix global inutile. Les filtres anciens devenus incompatibles sont réinitialisés.
- Suivi financier : les classes étaient déjà limitées côté serveur pour la capacité du module. Suppression du choix global lorsqu’une seule section est disponible et présélection de cette section, dans les deux vues de suivi.
- Personnel : l’absence d’affectation SECTION/CLASS explique légitimement qu’un chef de section ne voie pas un agent. Aucune affectation n’est créée automatiquement. Le SQL de lecture ne prenait que les affectations sans date de fin ; une fin prévue dans le futur était exclue trop tôt. Les lectures appliquent maintenant début <= aujourd’hui et fin absente ou > aujourd’hui. Une affectation terminée aujourd’hui reste terminée ; une affectation future ne donne pas d’accès anticipé. Le garde d’édition globale continue d’examiner les affectations partagées pertinentes.

## Limites et suite de l’audit
Ce lot ne certifie pas tous les modules. Il reste à inventorier les sélecteurs historiques sans capacité (notamment Communications et assistants de paramétrage), séparer les choix d’inscription et de consultation lorsque leurs permissions ont des périmètres différents, vérifier les exports et les liens profonds pour chaque rôle, et tester la réduction des droits avec les copies hors ligne déjà présentes. Les autorisations d’administration et les mutations restent soumises à leurs contrôles existants ; aucun rôle réel ni aucune donnée d’école n’a été modifié.

## Validation requise
Matrice : préfet secondaire, directeur primaire, direction maternelle/primaire réunies, rôle SCHOOL, droit ajouté avec SECTION, absence de périmètre, affectation absente/future/terminée/à fin future. Les tests utilisent des données fictives. Une vérification avec de vrais comptes de section en staging reste nécessaire avant certification globale ; un compte SCHOOL ne suffit pas à prouver l’isolement d’un préfet.
