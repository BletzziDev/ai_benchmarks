-- 005 (ACC-109): drop the redundant users.full_name column. DESTRUCTIVE: approved by the data owner
-- on the condition that data/accounts.db is backed up first (see PROGRESS.md / final report).
ALTER TABLE users DROP COLUMN full_name;
