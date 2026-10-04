from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def read(p): return (ROOT/p).read_text(encoding='utf-8')
def test_asset_column_matches_migration_and_count_is_fail_closed():
 r=read('backend/src/edusync/modules/stewardship/api/router.py')
 assert 'asset_tag,quantity' in r and 'asset_type_id,tag,quantity' not in r
 assert "Aucun comptage à valider" in r and "déjà validé" in r
 assert "@router.get('/counts')" in r and "@router.get('/counts/{count_id}')" in r
 assert "@router.get('/asset-types')" in r
def test_sync_admin_is_permission_driven_and_mounted_in_shell():
 a=read('frontend/src/App.tsx'); s=read('frontend/src/sync_admin.tsx')
 assert "sync:['sync.']" in a and "module==='sync'" in a
 assert "sync.device.register" in s and "sync.device.revoke" in s and "sync.conflicts.read" in s
def test_api_has_operational_stewardship_and_sync_clients():
 a=read('frontend/src/api.ts')
 for name in ['stewardshipAssetCreate','stewardshipAssetStatus','stewardshipCounts','stewardshipCountCreate','stewardshipCountLine','stewardshipCountValidate','syncStatus','syncDevices','syncDeviceRegister','syncDeviceRevoke','syncConflicts']:
  assert f'function {name}' in a
