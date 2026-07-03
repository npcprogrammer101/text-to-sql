-- ============================================================================
-- Read-only role for query execution.
--
-- The application executes every generated query as this user, which has
-- SELECT and nothing else. This is the database-level half of defense-in-depth:
-- even if a write somehow passed the guardrail, MySQL itself refuses it.
--
-- Run once as an admin/root user AFTER the data is loaded:
--   mysql -u root -p txt2sql < scripts/create_readonly_role.sql
--
-- Set a real password below (and put the matching READONLY_DATABASE_URL in .env).
-- ============================================================================

CREATE USER IF NOT EXISTS 'txt2sql_ro'@'localhost'
  IDENTIFIED BY 'CHANGE_ME_READONLY_PASSWORD';

-- SELECT only, on the txt2sql database.
GRANT SELECT ON txt2sql.* TO 'txt2sql_ro'@'localhost';

-- Explicitly ensure no write privileges linger.
REVOKE INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, INDEX, REFERENCES
  ON txt2sql.* FROM 'txt2sql_ro'@'localhost';

FLUSH PRIVILEGES;
