-- Certification Intendant (2026-10-30). The stewardship routes of decision 10 (LOCKED_OWNER_APPROVED) are now built:
-- asset edit and repair, stock Excel export, stock sheet, low-stock alerts, count export (Excel / PDF are aliases of
-- inventory.counts.export). Lifecycle change only, exactly like 0093: no role gains or loses a right. The holders are
-- those of the locked contracts — INTENDANT (all), GESTIONNAIRE and PROMOTEUR (read / export / print only).
UPDATE capability_catalog SET lifecycle = 'ACTIVE', updated_at = now()
 WHERE lifecycle = 'PLANNED' AND code IN ('inventory.assets.update', 'inventory.assets.repair.record', 'inventory.stock.export_xlsx',
                                         'inventory.stock.sheet.print', 'inventory.stock.low_alerts.read', 'inventory.counts.export');
