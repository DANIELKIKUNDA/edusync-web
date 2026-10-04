-- Platform health diagnostics only need delivery state, never recipients or content.
-- Column grants are provisioned separately. Tenant isolation remains unchanged.
DROP POLICY IF EXISTS communication_deliveries_platform_health ON communication_deliveries;
CREATE POLICY communication_deliveries_platform_health ON communication_deliveries
  FOR SELECT TO edusync_platform USING (true);
