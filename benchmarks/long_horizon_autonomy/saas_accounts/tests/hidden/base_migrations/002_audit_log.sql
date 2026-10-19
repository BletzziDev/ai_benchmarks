-- 002: audit log
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    actor_id INTEGER,
    action TEXT NOT NULL,
    target TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX audit_log_target ON audit_log(target);
