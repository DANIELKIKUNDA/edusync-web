/* Plain-French labels for technical codes shown to users (audit journal, statuses). The raw code stays
   available as a tooltip for support; it is never the main text. */
const ACTIONS: Record<string, string> = {
  PLATFORM_FIRST_MANAGER_CREATED: 'Premier Manager Système créé',
  PLATFORM_SCHOOL_CREATED: 'École créée',
  SCHOOL_CREATED: 'École créée',
  PLATFORM_SCHOOL_SUSPENDED: 'École suspendue',
  PLATFORM_SCHOOL_REACTIVATED: 'École réactivée',
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
};

function humanize(code: string) {
  const words = code.toLowerCase().split('_').filter(Boolean).join(' ');
  return words ? words[0].toUpperCase() + words.slice(1) : code;
}

export function auditActionLabel(code: string | null | undefined) {
  if (!code) return '—';
  return ACTIONS[code] || humanize(code);
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
