from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
FRONT=ROOT/'frontend'/'src'

def test_form_stack_is_centralized_on_form_surfaces():
    for name in ['App.tsx','login.tsx','personnel.tsx','schooling.tsx']:
        s=(FRONT/name).read_text(encoding='utf-8')
        assert 'react-hook-form' in s, name
        assert "from 'zod'" in s, name
        assert 'zodResolver' in s, name

def test_no_native_dialog_or_raw_exception_leak():
    src='\n'.join(p.read_text(encoding='utf-8') for p in FRONT.rglob('*.tsx'))
    for bad in ['window.prompt(', 'window.confirm(', 'window.alert(', 'String(e)', 'String(err)']:
        assert bad not in src

def test_shared_form_contract_has_accessible_inline_error():
    s=(FRONT/'platform'/'forms.tsx').read_text(encoding='utf-8')
    assert 'fieldError' in s and 'role="alert"' in s and 'shouldFocusError:true' in s

def test_key_legacy_forms_now_use_schema_driven_validation():
    app=(FRONT/'App.tsx').read_text(encoding='utf-8')
    personnel=(FRONT/'personnel.tsx').read_text(encoding='utf-8')
    schooling=(FRONT/'schooling.tsx').read_text(encoding='utf-8')
    # Closure 2026-10: the password form moved to platform/account.tsx (SecurityDialog), still schema-driven.
    account=(FRONT.parent.parent/'frontend/src/platform/account.tsx').read_text(encoding='utf-8')
    # Lot UX 2026-10: the unused inline school form was removed; schools are created by platform/school_create.tsx.
    school=(FRONT/'platform'/'school_create.tsx').read_text(encoding='utf-8')
    assert 'function validate(' in school and 'aria-invalid={!!errors[k]}' in school and 'role="alert"' in school and 'yearForm.handleSubmit' in app and 'form.handleSubmit' in account and 'zodResolver(passwordSchema)' in account
    assert 'function FunctionsPanel' in personnel and 'zodResolver(schema)' in personnel
    assert 'function EditStudent' in schooling and 'zodResolver(schema)' in schooling
