# Audit — École immédiatement exploitable sans configuration lourde

## Verdict

Le Desktop actuel contient déjà une bonne base d'industrialisation : référentiel scolaire RDC préchargé, types de frais connus, politiques de paiement/document/sauvegarde initialisées, numérotation automatique, contributions standards et assistant de mise en service. En revanche, le parcours courant reste encore **wizard-first** : nom d'école, année scolaire et au moins une section doivent être confirmés avant le parcours complet.

Pour EduSync Web, la cible recommandée est **progressive provisioning + readiness gates**, et non « tout configurer avant d'entrer dans l'application ».

## Ce qui doit être créé automatiquement au moment où Atelier Pro crée l'école

1. Tenant `school_id`, slug/code interne, statut ACTIVE/PREPARATION et identité minimale issue du formulaire Atelier Pro.
2. Premier Administrateur système école.
3. Référentiel RDC complet mais **non destructif** : sections, classes académiques, options, groupes tarifaires de référence.
4. Catalogue initial des types de frais déjà connu, sans créer de dette tant qu'aucun tarif applicable n'est confirmé.
5. Règles sûres : acomptes autorisés, monnaies FC/USD séparées, documents/reçus par défaut, sauvegarde, audit, idempotence, notifications internes.
6. Numérotation automatique des élèves/familles/reçus/rapports selon les contrats canoniques.
7. Arbre complet de capacités et rôles système de bootstrap uniquement; les rôles métier finaux seront décidés par Daniel au Point 3B.
8. Dossiers/documents et préférences de base.
9. Notifications internes actives. SMS externe désactivé tant qu'aucun fournisseur/solde/expéditeur n'est configuré.
10. Une année scolaire **suggérée en PREPARED**, jamais facturante par simple supposition. L'activation est une courte confirmation métier.

## Ce qui ne doit jamais être inventé automatiquement

- Les sections réellement organisées par l'école.
- Les classes réellement ouvertes cette année.
- Les montants des frais/tarifs.
- Une obligation d'admission payante si l'école ne l'a pas décidée.
- Une politique de réduction/exonération active.
- Les numéros de téléphone ou destinataires SMS.
- Une décision financière, un paiement ou un stock physique.

## Principe d'interface

Après création par Atelier Pro, l'administrateur entre directement dans EduSync. Aucun écran plein ne dit « système inutilisable tant que vous n'avez pas fini 25 paramètres ».

À la place, chaque domaine expose son état :

- **Prêt** : la fonction peut travailler immédiatement.
- **À confirmer** : valeurs sûres déjà proposées; une courte validation est nécessaire.
- **À compléter avant cette action** : seul le use case concerné est bloqué.
- **Non applicable** : l'école n'utilise pas cette fonction.

## Matrice minimale de readiness

| Domaine/action | Disponible juste après création | Prérequis ciblé |
|---|---:|---|
| Connexion / identité / utilisateurs / audit | Oui | aucun autre paramétrage métier |
| Personnel | Oui | aucun |
| Notifications internes | Oui | aucun |
| Communications SMS | Non pour l'envoi | fournisseur SMS + expéditeur/solde + destinataires |
| Consultation Paramètres | Oui | aucun |
| Année scolaire | Oui en PREPARED | confirmation pour ACTIVE |
| Structure/classes | Catalogue visible | sélectionner sections/classes réelles |
| Familles / prospects | Oui si on autorise dossier pré-admission | aucune facturation |
| Inscription annuelle | Non | année ACTIVE + classe ACTIVE |
| Effectifs | Oui mais vide | inscriptions |
| Tarifs | Écran prêt | montant réel à confirmer |
| Génération de charges | Non si aucun tarif | tarif applicable + année/classe |
| Encaissement | Non tant qu'aucune dette valide/caisse | charge valide + caisse ouverte |
| Encaissement CASH offline | Après armement | session caisse + autorisation offline + snapshot financier |
| Exports | Oui dès qu'une vue contient des données | permission de la vue + données |
| Intendance stocks | Oui | créer/importer le premier article de stock |
| Inventaire biens durables | Oui | créer/importer le premier bien |

## Décision d'architecture proposée

On remplace le concept global `configuration_completed >= 80%` comme verrou produit par des **Readiness Policies par use case**. Le pourcentage global peut rester comme indicateur de mise en service, mais il ne doit plus décider si l'école « peut utiliser EduSync ».

Exemples :

- `CanEnrollStudent`: année ACTIVE + classe ACTIVE.
- `CanGenerateSchoolFees`: barème applicable validé.
- `CanCollectPayment`: charge due + caisse ouverte + permission.
- `CanSendBulkSms`: fournisseur SMS opérationnel + permission bulk + destinataires valides.
- `CanRecordStockIssue`: article de stock actif + quantité suffisante ou politique de stock négatif explicitement interdite.

## Bénéfice industriel

Cette doctrine donne un produit qui paraît opérationnel dès sa création, tout en conservant des garde-fous stricts sur les rares éléments qu'un logiciel ne peut pas deviner pour l'école. Elle réduit fortement les abandons de configuration et évite les valeurs financières fictives.
