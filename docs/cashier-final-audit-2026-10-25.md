# Passe Caissier — état de la correction au 26/10/2026

Base : `f8d840a420644fcc3ae96ce9335081a17cabf8c6`. Travail dans une copie isolée. Aucun changement au VPS ni au module Recouvrement. **Caissier non certifié pour la production.**

## Corrections réalisées

- POS : écran à deux zones sur ordinateur, transaction et panier toujours visibles, recherche clavier, obligations futures repliées et action directe pour les priorités d'inscription. Sur mobile, barre permanente et feuille de transaction. File hors ligne ordonnée par séquence atomique IndexedDB, même si deux paiements ont le même horodatage. Brouillon familial conservé localement par école et utilisateur pendant 24 h, effacé à la déconnexion ; les soldes et priorités sont revérifiés avant encaissement.
- Excédent : opération atomique `collect-with-fund`, fondée sur les services d'encaissement et de fonds anticipés existants, avec clés d'idempotence et deux reçus distincts.
- Reçus : mise en file durable dans la transaction de paiement ; récupération du PDF sans faux statut « imprimé » ; statut imprimé uniquement après confirmation humaine ; répétition de la confirmation idempotente ; échec et reprise conservés. Après un paiement familial réussi, un échec du rafraîchissement du solde garde le succès visible et demande une actualisation avant une nouvelle opération. Le reçu Web 80 mm a été comparé visuellement au PDF Desktop de référence. Impression directe via le dialogue du navigateur ; la PWA ne garantit pas la sortie papier.
- Rapports officiels : aperçu séparé de la génération ; numéro, PDF archivé et index documentaire dans la même transaction SQL ; une clé de reprise rend exactement le même PDF et le même numéro. Un échec de stockage annule l'émission du numéro. Les profils particuliers `INSCRIPTION_JUIN` et `JOURNAL_ECUSSON` sont retirés des choix universels sans supprimer les documents historiques.
- Documents : vues personnelles et école filtrées côté serveur ; aperçu PDF dans EduSync ; lien signé téléchargé en mémoire pour éviter une expiration durant la lecture.
- Affichage : `FC` pour la devise technique `CDF`, dates communes au format `JJ/MM/AAAA`, navigation du tableau de bord corrigée. Le reçu mentionne le vrai caissier qui a encaissé.

Migrations : `0094_receipt_print_queue.sql`, `0095_official_report_archive_idempotency.sql`. Toutes deux sont ajoutées à `provision_database.py`.

## Vérifications effectuées

- Frontend : 14 fichiers de tests, 72 tests réussis ; TypeScript et build Vite réussis.
- Backend ciblé : 18 tests réussis après corrections, puis 6 tests de file/rapport réussis après la correction de confirmation répétée.
- Suite backend élargie : 743 tests passés avant une assertion ancienne sur le libellé monétaire ; elle a été adaptée à `FC`. Une relance complète a ensuite été interrompue par un test long dépendant de l'environnement Windows. Les contrôles CI Bash/Git ne sont pas exécutables fidèlement dans cette copie sans dépôt Git et environnement Linux.
- PostgreSQL local : migrations 0094 et 0095 exécutées sur un schéma de contrôle ; déclencheur de file, rollback, isolation RLS, droit UPDATE et unicité de clé de rapport vérifiés. La pile complète n'a pas été installée dans cette base locale.
- PDF Web 80 mm : structure et hiérarchie comparées visuellement au modèle Desktop. Formats 58 mm et A5 et imprimantes physiques non contrôlés.

## Certification PostgreSQL jetable sur Linux — 26/10/2026

La CI de la PR au commit `e077d7ab6e205a99f7f78d887a86d0d0d8675f2e` est verte : [run 40293597483](https://github.com/DANIELKIKUNDA/edusync-web/actions/runs/40293597483). Le nouveau test `tools/ci/cashier_postgres_integration.py` s'exécute après toutes les migrations sur PostgreSQL 16, avec les rôles owner et tenant de la CI. Il vérifie la mise en file du reçu dans la transaction du paiement, l'annulation d'un paiement dans un savepoint, l'isolation RLS entre écoles, l'émission et la lecture exacte d'un PDF officiel archivé, et l'annulation du numéro et du rapport lorsque le stockage est indisponible. Le stockage testé est l'adaptateur local sur disque jetable ; le stockage objet du staging et l'impression physique restent à certifier. Aucun VPS n'a été modifié par cette vérification.
## Scénarios critiques restant à certifier

1. Parcours réel sans scroll sur caisse desktop et sur Android, y compris inscription/réinscription mobile.
2. Excédent et rapport officiel sur PostgreSQL de la pile complète, avec object storage et plusieurs utilisateurs réels.
3. Paiement hors ligne, fermeture de la PWA, reprise réseau et absence de doublon serveur sur appareils réels.
4. Documents multi-rôles, signatures selon type de document et impression papier sur périphériques réels.
5. Fuseau horaire configuré pour l'école : la salutation actuelle suit l'heure locale de l'appareil.
6. Catalogue de rapports configurable par école, passe globale des libellés/dates/clavier et mesures de performance avant/après.

Le « responsable financier prévu par élève » reste une annotation de l'inscription distincte des prises en charge d'obligation et des préférences de retenue sur paie du personnel. Aucune fusion métier de ces trois concepts n'a été tentée.
