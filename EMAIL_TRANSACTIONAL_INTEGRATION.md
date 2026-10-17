# E-mail transactionnel

Statut : **prêt, `EMAIL_REAL_PROVIDER_CERTIFIED` = NON** tant qu'aucun relais SMTP réel n'est configuré et que
`email_provider_probe` n'a pas été exécuté.

## 1. Fournisseur

`EmailProviderPort` ; adaptateur initial **SMTP standard** (`aiosmtplib`, messages construits avec `EmailMessage`).
Tout relais professionnel convient sans toucher à l'IAM (Brevo SMTP, Mailjet, Amazon SES SMTP, relais d'entreprise).
Chiffrement obligatoire hors développement : `starttls` (587) ou `tls` (465). Les modèles utilisent la bibliothèque
standard avec échappement HTML de chaque valeur (Jinja2 n'étant pas déjà présent, aucune dépendance ajoutée).

`SENT` = le serveur SMTP a accepté le message (identifiant = notre `Message-ID`) ; **jamais `DELIVERED`**. Les
webhooks de rebond / livraison d'un futur fournisseur iront dans un adaptateur spécialisé, sans casser le port.

## 2. Cas couverts

| Cas | Règle |
|---|---|
| Invitation d'un membre | « Accès & rôles » → *Invitation par e-mail* : aucun mot de passe montré ni envoyé ; lien unique, valable **48 h**, utilisable une fois ; la personne choisit son mot de passe |
| Mot de passe oublié | réponse identique que l'adresse existe ou non (pas d'énumération) ; lien valable **30 min**, usage unique ; uniquement pour un compte école actif (les comptes plateforme passent par un Manager Système, second facteur oblige) ; limité à 5 demandes / heure / IP |
| Réinitialisation | nouveau mot de passe ; toutes les sessions et tous les appareils push de la personne sont fermés ; les autres liens ouverts sont révoqués |
| Alertes de sécurité | changement / réinitialisation du mot de passe : e-mail sans donnée sensible |

Jetons : 256 bits aléatoires (`secrets.token_urlsafe(32)`), seule l'empreinte SHA-256 est stockée
(`account_tokens.token_hash`), consommation sous verrou (rejeu refusé), un nouveau lien révoque le précédent. Le lien
voyage dans le **fragment d'URL** (`#reset=…`, `#invitation=…`) : jamais dans une ligne de requête, un journal ou un
Referer ; la page le lit une fois et le retire de la barre d'adresse. En attendant l'envoi, le lien est chiffré sur la
ligne du destinataire (AES-256-GCM) puis effacé par le worker. Durées configurables :
`EDUSYNC_INVITATION_TTL_HOURS`, `EDUSYNC_PASSWORD_RESET_TTL_MINUTES`.

Sans fournisseur e-mail, l'ancien parcours reste disponible : mot de passe provisoire affiché une fois.

## 3. Paramètres SMTP à fournir (quand le relais sera choisi)

`EDUSYNC_EMAIL_PROVIDER=smtp`, `EDUSYNC_SMTP_HOST`, `EDUSYNC_SMTP_PORT`, `EDUSYNC_SMTP_USERNAME`,
`EDUSYNC_SMTP_PASSWORD` (secret, worker uniquement), `EDUSYNC_SMTP_FROM_EMAIL` (domaine vérifié : SPF, DKIM, DMARC
chez le relais), `EDUSYNC_SMTP_FROM_NAME`, `EDUSYNC_SMTP_SECURITY`, et `EDUSYNC_PUBLIC_APP_URL` (HTTPS) pour les liens.
Sonde réelle : `EDUSYNC_PROBE_EMAIL_TO` = votre propre boîte de test.
