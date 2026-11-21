DELETE FROM rbac_role_capabilities WHERE capability_code='subscription.account.read';
DELETE FROM capability_catalog WHERE code='subscription.account.read';

