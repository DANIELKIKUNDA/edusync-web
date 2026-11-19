"""Operational picker metadata, scoped to one capability, independently of other rights."""

def scoped_structure(sections, classes, options, scopes):
    school = any(kind == 'SCHOOL' for kind, _ in scopes)
    section_codes = {str(v).upper() for kind, v in scopes if kind in ('SECTION', 'CYCLE') and v}
    class_codes = {str(v).upper() for kind, v in scopes if kind == 'CLASS' and v}
    visible_classes = [c for c in classes if school or str(c.get('section_code', '')).upper() in section_codes or str(c.get('code', '')).upper() in class_codes]
    section_ids = {str(c['section_id']) for c in visible_classes}
    option_ids = {str(c.get('option_id')) for c in visible_classes if c.get('option_id')}
    visible_sections = [s for s in sections if school or str(s['code']).upper() in section_codes or str(s['id']) in section_ids]
    full_section_ids = {str(s['id']) for s in sections if str(s['code']).upper() in section_codes}
    visible_options = [o for o in options if school or str(o['section_id']) in full_section_ids or str(o['id']) in option_ids]
    return {'school_wide': school, 'sections': visible_sections, 'classes': visible_classes, 'options': visible_options}
