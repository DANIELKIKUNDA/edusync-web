# Point 3B — politiques de périmètre et propriété des opérations

## Chef de section
Le rôle fonctionnel est commun. `PREFET_ETUDES` vise normalement la section Secondaire. `DIRECTION_SECTION` vise Primaire/Maternelle; une affectation peut couvrir plusieurs sections. Tous les accès élèves, personnel, Finance de lecture et communications doivent passer par le résolveur de périmètre métier avant IAM.

## Caissier — caisse
`finance.cash.read` signifie **sa caisse/session** dans le contexte Caissier. `finance.cash.other.read` n'est pas accordé au rôle standard Caissier. `finance.dashboard.read` peut exposer un total école agrégé CDF/USD, sans ventilation détaillée des autres caissiers.

## Caissier — correction de paiement
`finance.payments.reverse` n'autorise jamais UPDATE/DELETE d'un paiement. Le use case exige: paiement original conservé, motif obligatoire, audit, contre-écriture/réversal, reçu original marqué annulé/corrigé, puis éventuelle nouvelle opération. Le rôle standard Caissier ne peut l'utiliser que sur **son propre paiement** et tant que **sa caisse est ouverte**. Caisse clôturée ou opération d'un autre caissier => permission/workflow supérieur.

## Promoteur/Gestionnaire
Les capacités de lecture n'impliquent aucune mutation. `communications.read/history` permet seulement de contrôler les communications; aucun envoi parent n'est accordé au Promoteur/Gestionnaire standard.

## Rôles personnalisés
Les rôles standards ne sont pas modifiés par une école. Pour adapter la réalité locale, l'Administrateur système autorisé clone un rôle standard vers `SCHOOL_CUSTOM`, puis l'école choisit les capacités et périmètres. Cela garde une baseline produit stable et auditable.
