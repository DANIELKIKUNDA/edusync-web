/* Plain-French labels for technical codes shown to users (audit journal, statuses). The raw code stays
   available as a tooltip for support; it is never the main text. */
const ACTIONS: Record<string, string> = {
  COMMUNICATION_SMS_BULK_REQUESTED: 'Envoi groupé de SMS demandé',
  COMMUNICATION_REQUESTED: 'Message demandé',
  COMMUNICATION_SETTINGS_UPDATED: 'Réglages de communication modifiés',
  ACCESS_MEMBER_CREATED: 'Membre ajouté à l’école',
  ACCESS_MEMBER_UPDATED: 'Membre de l’école modifié',
  ACCESS_ROLE_CREATED: 'Rôle d’école créé',
  ACCESS_ROLE_UPDATED: 'Rôle d’école modifié',
  PLATFORM_MESSAGING_TEST_SENT: 'Message de test envoyé',
  SCHOOL_IDENTITY_UPDATED: 'Identité de l’école modifiée',
  USER_LOGOUT: 'Déconnexion',
  USER_LOGOUT_ALL: 'Déconnexion de tous les appareils',
  PASSWORD_RESET: 'Mot de passe réinitialisé',
  USER_AVATAR_UPDATED: 'Photo de profil modifiée',
  USER_AVATAR_REMOVED: 'Photo de profil retirée',
  PLATFORM_FIRST_MANAGER_CREATED: 'Premier Manager Système créé',
  PLATFORM_SCHOOL_CREATED: 'École créée',
  SCHOOL_CREATED: 'École créée',
  PLATFORM_SCHOOL_SUSPENDED: 'École suspendue',
  PLATFORM_SCHOOL_REACTIVATED: 'École réactivée',
  PLATFORM_SCHOOL_UPDATED: 'Fiche école modifiée',
  PLATFORM_SCHOOL_ADMIN_ACCESS_RESET: 'Accès administrateur réinitialisé',
  PLATFORM_SCHOOLS_EXPORTED: 'Liste des écoles exportée',
  PLATFORM_SCHOOL_ADMIN_BOOTSTRAPPED: 'Administrateur initial créé',
  SCHOOL_ADMIN_BOOTSTRAPPED: 'Administrateur initial créé',
  PLATFORM_ROLE_ASSIGNED: 'Rôle attribué',
  PLATFORM_ROLE_REVOKED: 'Rôle retiré',
  PLATFORM_MEMBERSHIP_DEACTIVATED: 'Accès désactivé',
  PLATFORM_MEMBERSHIP_REACTIVATED: 'Accès réactivé',
  PLATFORM_COLLABORATOR_GRANTED: 'Accès collaborateur accordé',
  PLATFORM_COLLABORATOR_REVOKED: 'Accès collaborateur retiré',
  PLATFORM_SYSTEM_NOTIFICATION_SENT: 'Notification système envoyée',
  SCHOOL_LOGO_UPDATED: 'Logo de l’école modifié',
  PRINT_SETTINGS_UPDATED: 'Réglage d’impression modifié',
  FINANCE_RECEIPT_PRINTED: 'Reçu imprimé',
  FINANCE_RECEIPT_REPRINTED: 'Duplicata de reçu imprimé',
  COMMUNICATION_TEMPLATE_SAVED: 'Modèle de message enregistré',
  COMMUNICATION_DELIVERY_RETRIED: 'Envoi de SMS relancé',
  USER_LOGIN: 'Connexion',
  PASSWORD_CHANGED: 'Mot de passe modifié',
  SESSIONS_REVOKED_ALL: 'Déconnexion de tous les appareils',
  MFA_ENROLLMENT_STARTED: 'Validation en deux étapes : configuration commencée',
  MFA_ENROLLED: 'Validation en deux étapes activée',
  MFA_VERIFIED: 'Connexion confirmée par code de vérification',
  MFA_RECOVERY_CODE_USED: 'Connexion par code de secours',
  MFA_RECOVERY_CODES_REGENERATED: 'Nouveaux codes de secours générés',
  MFA_FAILED: 'Code de vérification refusé',
  MFA_LOCKED: 'Validation en deux étapes verrouillée (trop d’essais)',
  PLATFORM_USER_MFA_RESET: 'Validation en deux étapes réinitialisée par un Manager',
  MFA_STEP_UP: 'Action sensible confirmée par code',
  PLATFORM_USER_MFA_RESET_BY_OPERATOR: 'Validation en deux étapes réinitialisée par l’opérateur (procédure de secours)',
  SCHOOL_SUSPENDED: 'École suspendue',
  SCHOOL_REACTIVATED: 'École réactivée',
  PLATFORM_NOTIFICATION_CAMPAIGN_SENT: 'Notification envoyée',
  PLATFORM_AUDIT_EXPORTED: 'Audit exporté',
  PLATFORM_STANDARD_ROLE_ASSIGNED: 'Rôle école attribué',
  PLATFORM_STANDARD_ROLE_REVOKED: 'Rôle école retiré',
  SESSION_REVOKED: 'Appareil déconnecté',
  PLATFORM_ROLE_CREATED: 'Rôle plateforme créé',
  PLATFORM_ROLE_UPDATED: 'Rôle plateforme modifié',
  PLATFORM_ROLE_ACTIVATED: 'Rôle plateforme activé',
  PLATFORM_ROLE_ARCHIVED: 'Rôle plateforme archivé',
  PLATFORM_ROLE_CLONED: 'Rôle plateforme cloné',
  PLATFORM_USER_CREATED: 'Membre de l’équipe ajouté (nouvelle identité)',
  PLATFORM_MEMBER_ADDED: 'Accès plateforme donné à un compte existant',
  PLATFORM_ACCESS_REVOKED: 'Accès plateforme retiré',
  PLATFORM_CAPABILITY_GRANTED: 'Capacité supplémentaire attribuée',
  PLATFORM_CAPABILITY_REVOKED: 'Capacité supplémentaire retirée',
  PLATFORM_CAPABILITY_GRANT_EXPIRED: 'Capacité supplémentaire arrivée à échéance',
  PLATFORM_INVITATION_RESENT: 'Invitation renvoyée',
  PLATFORM_USER_SUSPENDED: 'Compte plateforme suspendu',
  PLATFORM_USER_REACTIVATED: 'Compte plateforme réactivé',
  PLATFORM_USER_PASSWORD_RESET: 'Mot de passe réinitialisé',
  PLATFORM_USER_SESSION_REVOKED: 'Appareil d’un membre déconnecté',
  PLATFORM_USER_SESSIONS_REVOKED: 'Tous les appareils d’un membre déconnectés',
};

function humanize(code: string) {
  const words = code.toLowerCase().split('_').filter(Boolean).join(' ');
  return words ? words[0].toUpperCase() + words.slice(1) : code;
}

// School administration journal (2026-10-23): never show a technical code to an end user.
const SCHOOL_ACTIONS: Record<string, string> = {
  ACADEMIC_YEAR_ACTIVATED: 'Année scolaire activée', ACADEMIC_YEAR_ARCHIVED: 'Année scolaire archivée', ACADEMIC_YEAR_CLOSED: 'Année scolaire clôturée',
  ACADEMIC_YEAR_CONFIGURATION_COPIED: 'Configuration reprise de l’année précédente', ACADEMIC_YEAR_CREATED: 'Année scolaire préparée',
  ACADEMIC_YEAR_REOPENED: 'Année scolaire rouverte', ACADEMIC_YEAR_UPDATED: 'Année scolaire modifiée',
  SETTINGS_ACTIVATE_ACADEMIC_YEAR: 'Année scolaire activée', SETTINGS_ADMISSION_CONDITION_ACTIVE: 'Condition d’admission activée ou suspendue',
  SETTINGS_ADMISSION_REVIEW: 'Conditions d’admission revues', SETTINGS_ANTICIPATION_PLAN_ACTIVE: 'Plan anticipé activé ou suspendu',
  SETTINGS_APPLY_TARIFFS: 'Barèmes appliqués aux classes', SETTINGS_CLASS_STATUS: 'Classe ouverte ou fermée',
  SETTINGS_COPY_ACADEMIC_YEAR_CONFIGURATION: 'Configuration reprise de l’année précédente', SETTINGS_CREATE_ACADEMIC_YEAR: 'Année scolaire préparée',
  SETTINGS_CREATE_CLASS: 'Classe ouverte', SETTINGS_CREATE_CONTRIBUTION: 'Contribution en nature créée', SETTINGS_CREATE_FEE_TYPE: 'Type de frais créé',
  SETTINGS_FEE_TYPE_CREATED: 'Type de frais créé', SETTINGS_CREATE_PRODUCT: 'Article scolaire créé', SETTINGS_CREATE_TARIFF: 'Tarif créé',
  SETTINGS_PUT_ADMISSION_CONDITION: 'Condition d’admission enregistrée', SETTINGS_PUT_ANTICIPATION_PLAN: 'Plan anticipé enregistré',
  SETTINGS_PUT_BENEFIT_POLICY: 'Politique d’avantages enregistrée', SETTINGS_PUT_BILLING_POLICY: 'Mois de facturation enregistrés',
  SETTINGS_PUT_PAYMENT_POLICY: 'Règles d’encaissement enregistrées', SETTINGS_PUT_TARIFF_RULE: 'Règle tarifaire enregistrée',
  SETTINGS_UPDATE_ACADEMIC_YEAR: 'Année scolaire modifiée', SETTINGS_UPDATE_CLASS: 'Classe modifiée', SETTINGS_UPDATE_CONTRIBUTION: 'Contribution modifiée',
  SETTINGS_UPDATE_FEE_TYPE: 'Type de frais modifié', SETTINGS_UPDATE_IDENTITY: 'Identité de l’école modifiée', SETTINGS_UPDATE_PRODUCT: 'Article modifié',
  SETTINGS_UPDATE_TARIFF: 'Tarif modifié', SETTINGS_UPSERT_OPTION: 'Option enregistrée', SETTINGS_UPSERT_SECTION: 'Section enregistrée',
  ACCESS_ROLE_ASSIGNED: 'Rôle attribué', ACCESS_ROLE_REVOKED: 'Rôle retiré', ACCESS_ROLE_CREATED: 'Rôle créé', ACCESS_ROLE_UPDATED: 'Rôle modifié',
  ACCESS_ROLE_ARCHIVED: 'Rôle archivé', ACCESS_ROLE_POLICY_UPDATED: 'Rôle ajusté pour l’école', ACCESS_ROLE_CONVERTED: 'Rôle converti en rôle standard',
  ACCESS_MEMBER_CREATED: 'Compte créé', ACCESS_MEMBER_ATTACHED: 'Compte rattaché', ACCESS_MEMBER_UPDATED: 'Membre modifié',
  ACCESS_MEMBER_DEACTIVATED: 'Membre désactivé', ACCESS_MEMBER_ACTIVATED: 'Membre réactivé', ACCESS_MEMBER_CREDENTIALS_RESET: 'Mot de passe réinitialisé',
  ACCESS_CHANGE_REQUESTED: 'Demande d’approbation', ACCESS_CHANGE_APPROVED: 'Demande approuvée', ACCESS_CHANGE_REJECTED: 'Demande refusée',
  ACCESS_CHANGE_CANCELLED: 'Demande retirée', ACCESS_SOD_RULE_UPDATED: 'Règle de séparation des tâches modifiée',
  // School journal (2026-10-28): every business action recorded by the server reads as a sentence.
  ADMISSION_CONDITION_DEACTIVATED: 'Condition d’admission désactivée', ADMISSION_CONDITION_SAVED: 'Condition d’admission enregistrée', ADMISSION_CONDITIONS_REVIEWED: 'Conditions d’admission revues',
  ADVANCE_FUND_REMBOURSEMENT: 'Avance remboursée', ALLOCATE_ADVANCE_FUND: 'Avance affectée aux frais', RECEIVE_ADVANCE_FUND: 'Avance reçue',
  ANTICIPATION_MEMBERSHIP_SET: 'Adhésion à un plan anticipé', ANTICIPATION_PAYMENT_RECORDED: 'Paiement anticipé enregistré', ANTICIPATION_PLAN_SAVED: 'Plan anticipé enregistré',
  BENEFIT_POLICY_SAVED: 'Politique d’avantages enregistrée', BILLING_MONTHS_UPDATED: 'Mois de facturation modifiés',
  CREATE_FINANCIAL_DECISION: 'Décision financière prise', CANCEL_FINANCIAL_DECISION: 'Décision financière annulée',
  CANCEL_STAFF_NONCASH_SETTLEMENT: 'Retenue sur salaire annulée', CONFIRM_STAFF_PAYROLL_DEDUCTION: 'Retenue sur salaire confirmée',
  CLOSE_CASH_DAY: 'Journée de caisse clôturée', REOPEN_CASH_DAY: 'Journée de caisse rouverte', RECORD_EXPENSE: 'Dépense de caisse enregistrée',
  PAYMENT_ANNULATION: 'Paiement annulé', PAYMENT_REMBOURSEMENT: 'Paiement remboursé', PAYMENT_POLICY_SAVED: 'Règles d’encaissement enregistrées',
  FINANCE_RECEIPT_REPRINTED: 'Reçu réimprimé', SET_CHARGE_RESPONSIBILITY: 'Responsable du paiement défini', GENERATE_PERIODIC_REPORT: 'Rapport financier officiel généré',
  FINANCIAL_HISTORY_IMPORT_ANALYZED: 'Reprise financière analysée', FINANCIAL_HISTORY_IMPORT_EXECUTED: 'Reprise financière exécutée',
  OFFLINE_FINANCE_LEASE_ACTIVE: 'Caisse hors ligne activée', OFFLINE_FINANCE_LEASE_PREPARING: 'Caisse hors ligne en préparation',
  COMMUNICATION_DELIVERY_RETRIED: 'Envoi de message relancé', COMMUNICATION_SETTINGS_UPDATED: 'Canaux de communication modifiés',
  COMMUNICATION_SMS_BULK_REQUESTED: 'SMS groupés demandés', COMMUNICATION_TEMPLATE_SAVED: 'Modèle de message enregistré',
  SMS_WALLET_ADJUSTMENT: 'Solde SMS ajusté', SMS_WALLET_TOPUP: 'Solde SMS rechargé',
  'contribution.recorded': 'Dépôt matériel enregistré', CONTRIBUTION_TYPE_CREATED: 'Contribution en nature créée',
  DOCUMENT_SETTINGS_UPDATED: 'Réglages des documents modifiés', PRINT_SETTINGS_UPDATED: 'Réglages d’impression modifiés',
  ENROLLMENT_POLICY_UPDATED: 'Règles d’inscription modifiées', ENROLLMENT_WINDOW_UPDATED: 'Période d’inscription modifiée',
  FAMILY_ENROLLMENT_COMPLETED: 'Inscription d’une famille', FEE_TYPE_UPDATED: 'Type de frais modifié', INVENTORY_ITEM_CREATED: 'Article d’inventaire créé',
  SCHOOL_CLASS_CREATED: 'Classe ouverte', SCHOOL_CLASS_STATUS_CHANGED: 'Classe ouverte ou fermée', SCHOOL_CLASS_UPDATED: 'Classe modifiée',
  SCHOOL_DATA_EXPORT_TESTED: 'Sauvegarde testée', SCHOOL_DATA_EXPORTED: 'Données de l’école sauvegardées', SCHOOL_DIAGNOSTIC_EXPORTED: 'Diagnostic exporté',
  SCHOOL_IDENTITY_UPDATED: 'Identité de l’école modifiée', SCHOOL_LOGO_UPDATED: 'Logo de l’école modifié', SCHOOL_OPTION_UPSERTED: 'Option enregistrée',
  SCHOOL_PRODUCT_CREATED: 'Article scolaire créé', SCHOOL_PRODUCT_UPDATED: 'Article scolaire modifié', SCHOOL_SECTION_UPSERTED: 'Section enregistrée',
  STAFF_ACCESS_LINKED: 'Agent relié à un compte', STAFF_ASSIGNMENT_ADDED: 'Affectation d’un agent', STAFF_CHILD_FINANCE_MODE_CHANGED: 'Mode de paiement d’un enfant du personnel modifié',
  STAFF_CHILD_LINKED: 'Enfant du personnel relié', STAFF_CREATED: 'Agent ajouté au personnel', STAFF_EXITED: 'Départ d’un agent',
  STAFF_FUNCTION_CREATED: 'Fonction créée', STAFF_IMPORT_ANALYZED: 'Import du personnel analysé', STAFF_IMPORT_EXECUTED: 'Import du personnel exécuté', STAFF_UPDATED: 'Agent modifié',
  STUDENT_ABANDON: 'Abandon d’un élève', STUDENT_CLASS_CHANGED: 'Changement de classe', STUDENT_IMPORT_ANALYZED: 'Import d’élèves analysé',
  STUDENT_IMPORT_EXECUTED: 'Import d’élèves exécuté', STUDENT_PROFILE_UPDATED: 'Fiche élève modifiée', STUDENT_REINTEGRATE: 'Réintégration d’un élève',
  STUDENT_SUSPEND: 'Suspension d’un élève', STUDENT_TRANSFER: 'Transfert d’un élève',
  TARIFF_CREATED: 'Tarif créé', TARIFF_RULE_UPSERTED: 'Règle tarifaire enregistrée', TARIFFS_APPLIED: 'Barèmes appliqués aux classes',
  PASSWORD_CHANGED: 'Mot de passe changé', PASSWORD_REPLACED_AFTER_TEMPORARY: 'Mot de passe provisoire remplacé', SESSION_REVOKED: 'Session fermée à distance',
  SESSIONS_REVOKED_ALL: 'Toutes les sessions fermées', USER_AVATAR_UPDATED: 'Photo de profil modifiée', INVITATION_ACCEPTED: 'Invitation acceptée',
  CONTEXT_SWITCHED: 'Changement d’école', CONTEXT_SWITCH_REFUSED: 'Changement d’école refusé',
};

export function auditActionLabel(code: string | null | undefined) {
  if (!code) return '—';
  if (SCHOOL_ACTIONS[code]) return SCHOOL_ACTIONS[code];
  if (ACTIONS[code]) return ACTIONS[code];
  if (/^SETTINGS_/.test(code)) return 'Paramètre modifié';
  if (/^ACCESS_/.test(code)) return 'Accès modifié';
  return humanize(code);
}

export function resultLabel(code: string | null | undefined) {
  return code === 'SUCCESS' ? 'Réussi' : code === 'REJECTED' ? 'Refusé' : code === 'FAILED' ? 'Échec' : (code || '—');
}

export function schoolStatusLabel(code: string | null | undefined) {
  return code === 'ACTIVE' ? 'Active' : code === 'SUSPENDED' ? 'Suspendue' : code === 'DISABLED' ? 'Désactivée' : code === 'DRAFT' ? 'En préparation' : (code || '—');
}

export function severityLabel(code: string | null | undefined) {
  return code === 'CRITICAL' ? 'Critique' : code === 'WARNING' ? 'Avertissement' : code === 'INFO' ? 'Information' : (code || '—');
}

export function yearStatusLabel(code: string | null | undefined) {
  return code === 'ACTIVE' ? 'En cours' : code === 'PREPARED' ? 'Préparée' : code === 'CLOSED' ? 'Clôturée' : code === 'ARCHIVED' ? 'Archivée' : (code || '—');
}

// Sync / outbox event types shown in the synchronisation screen.
Object.assign(ACTIONS,{COMMUNICATION_REQUESTED:'Message à envoyer',PAYMENT_RECORDED:'Paiement enregistré',STUDENT_ENROLLED:'Élève inscrit',communication_message:'message',finance_payment:'paiement'});
