ALTER TABLE school_print_settings DROP CONSTRAINT IF EXISTS school_print_settings_format_ck;
ALTER TABLE school_print_settings ADD CONSTRAINT school_print_settings_format_ck
  CHECK (receipt_format IN ('A4', 'A5', '80MM', '58MM'));
