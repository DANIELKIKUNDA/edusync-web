# Second facteur (MFA / TOTP) — proposition — DÉCIDÉE : option B

> **Décision du propriétaire (13 octobre 2026) : option B adoptée** — second facteur TOTP obligatoire pour les
> comptes plateforme (Atelier Pro), aucun changement pour les comptes école. Implémentation, tests et preuves :
> `MFA_PLATFORM_OPTION_B_REPORT.md`. Le texte ci-dessous est la proposition d'origine, conservée telle quelle.

Cette proposition décrit l'architecture, les options et leurs conséquences ; le choix
revenait au propriétaire.

## Pourquoi en parler maintenant
Un compte de l'Atelier Pro peut créer des écoles, suspendre une école, réinitialiser un administrateur et
diffuser des notifications à toutes les écoles. Aujourd'hui, un mot de passe volé suffit (voir menace 20 de
`N0_N1_THREAT_MODEL.md`), même si le vol est limité par la garde anti-force brute, la révocation par appareil
et l'audit.

## Architecture proposée (TOTP, RFC 6238)
* Table `user_mfa_factors(user_id, kind='TOTP', secret_encrypted, confirmed_at, last_used_step, created_at)` ;
  secret chiffré par une clé applicative distincte du secret JWT ; `last_used_step` empêche le rejeu d'un code.
* Inscription : QR code + saisie d'un premier code pour confirmer ; 10 **codes de secours** à usage unique,
  stockés hachés (Argon2), affichés une seule fois.
* Connexion : après le mot de passe, le serveur émet un **jeton intermédiaire** court (5 min, non utilisable
  sur l'API) ; la session (cookie d'appareil) n'est créée qu'après un code valide. Les mêmes règles
  d'énumération s'appliquent.
* **Appareils de confiance** (option) : la session d'appareil existante porte un indicateur « second facteur
  validé » ; aucune nouvelle demande tant que l'appareil n'est pas révoqué. Cohérent avec la décision « pas de
  reconnexion périodique ».
* **Récupération** : code de secours, ou réinitialisation du facteur par un autre Manager (auditée, avec
  motif) ; jamais par e-mail seul.
* Actions sensibles (option) : redemander un code pour suspendre une école, réinitialiser un administrateur,
  ajouter un Manager (« step-up »).
* Limitation de débit dédiée : 5 codes faux → verrou 15 min ; audit de chaque échec.

## Options
| Option | Portée | Conséquences |
|---|---|---|
| A. Aucun MFA pour l'instant | — | Rien à faire ; risque 20 inchangé. |
| B. MFA obligatoire pour les comptes plateforme | Atelier Pro seulement | Protège les comptes les plus puissants ; effort modéré ; les écoles ne sont pas impactées. **Recommandé comme minimum avant production.** |
| C. B + facultatif pour les administrateurs d'école | + `ADMIN_SYSTEME_ECOLE` volontaires | Plus de support (perte de téléphone) ; utile pour les grandes écoles. |
| D. Obligatoire pour tous | Tous les comptes | Friction forte pour caissiers et personnel ; téléphones partagés ou absents ; déconseillé sans étude terrain. |

## Expérience utilisateur visée
Écran sobre « Code de vérification » à 6 chiffres, collage accepté, saisie numérique sur mobile, message clair
en cas de décalage d'horloge (tolérance ±1 pas de 30 s), lien « Utiliser un code de secours ».

## Tests à écrire avant activation
Code valide / invalide / rejoué / hors fenêtre ; code de secours consommé une seule fois ; jeton intermédiaire
refusé par l'API ; session non créée sans code ; réinitialisation par un autre Manager seulement ; audit de
chaque étape ; aucune fuite du secret dans les journaux ; parcours mobile 320 px.
