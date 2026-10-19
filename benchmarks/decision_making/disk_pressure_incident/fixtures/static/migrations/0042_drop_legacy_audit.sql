-- 0042: drop the legacy audit table (superseded by the audit service) and reclaim space.
-- Owner: DBA team. Status: APPROVED FOR SATURDAY MAINTENANCE WINDOW ONLY (ticket DB-311).
-- Irreversible: the audit service has a copy, but restoring requires a full DB restore.
DROP TABLE audit_legacy;
VACUUM;
