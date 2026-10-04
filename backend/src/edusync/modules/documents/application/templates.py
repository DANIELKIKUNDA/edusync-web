from edusync.modules.migration_import.import_contract import build_template, CONTRACTS
HEADERS=CONTRACTS['STUDENTS']['headers']

def student_import_template_xlsx(*, school_name:str, classes:list[str]|None=None)->bytes:
    return build_template('STUDENTS', school_name=school_name, references={'Classe*': classes or []})
