-- 004 (ACC-109): split users.full_name into first_name / last_name. Additive and backfilled.
ALTER TABLE users ADD COLUMN first_name TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN last_name TEXT NOT NULL DEFAULT '';
UPDATE users SET
    first_name = CASE WHEN instr(trim(full_name), ' ') > 0
                      THEN substr(trim(full_name), 1, instr(trim(full_name), ' ') - 1)
                      ELSE trim(full_name) END,
    last_name  = CASE WHEN instr(trim(full_name), ' ') > 0
                      THEN trim(substr(trim(full_name), instr(trim(full_name), ' ') + 1))
                      ELSE '' END;
