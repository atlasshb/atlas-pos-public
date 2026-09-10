-- =============================================================================
-- Atlas POS program — create the READ-ONLY mirror user on an DoPos terminal
-- -----------------------------------------------------------------------------
-- This is the manual L1 step every mirror depends on. Run it ONCE per terminal,
-- locally, as a MySQL admin (root) on the client's DoPos box. It creates a
-- dedicated user that can ONLY read the DoPos database — no writes, no
-- GRANT, no access to any other schema. pos-mirror.sh connects as this user.
--
-- BEFORE YOU RUN:
--   * Do this only with the client's consent (preparation step; read-only, but it
--     touches a LIVE card-payment box).
--   * Replace the three placeholders below:
--       <dopos_DB>   the DoPos database name (e.g. dopos)
--       <RO_PASSWORD>  a strong random password (this is MYSQL_PW in the env file)
--     The host part of the user is pinned to the tailnet CGNAT range 100.%.%.%
--     so this credential can ONLY be used from the Atlas hub over Tailscale, not
--     from the open LAN.
--
-- WHY scoped to the db, not *.*:
--   A global GRANT SELECT ON *.* would also expose mysql.user (password hashes)
--   and every other schema on the box. We scope to the ONE DoPos database.
--   SHOW VIEW / TRIGGER / EVENT are added because mysqldump needs them to capture
--   views, triggers and events (the dump uses --routines --triggers --events).
-- =============================================================================

-- 1) Create the user, locked to the tailnet host range only.
--    (MySQL 8: CREATE USER. MariaDB: identical syntax works.)
CREATE USER IF NOT EXISTS 'atlas_ro'@'100.%.%.%'
  IDENTIFIED BY '<RO_PASSWORD>';

-- 2) Grant ONLY the read privileges mysqldump needs, scoped to the DoPos db.
--    SELECT        : read table rows
--    SHOW VIEW     : dump view definitions
--    TRIGGER       : dump triggers (--triggers)
--    EVENT         : dump events  (--events)
--    EXECUTE       : allow --routines to read stored procedures/functions
--    LOCK TABLES   : intentionally OMITTED — the mirror uses --single-transaction
--                    + --skip-lock-tables and must NEVER lock the live POS.
GRANT SELECT, SHOW VIEW, TRIGGER, EVENT, EXECUTE
  ON `<dopos_DB>`.*
  TO 'atlas_ro'@'100.%.%.%';

-- 3) Apply.
FLUSH PRIVILEGES;

-- =============================================================================
-- VERIFY (run these after creating the user; expected results in comments).
-- =============================================================================

-- A) Confirm the grants are read-only and scoped to the one database.
--    Expect to see only: GRANT SELECT, SHOW VIEW, TRIGGER, EVENT, EXECUTE
--    ON `<dopos_DB>`.* — and a USAGE line. NO "ALL PRIVILEGES", NO "*.*",
--    NO "WITH GRANT OPTION", NO INSERT/UPDATE/DELETE/DROP/CREATE.
SHOW GRANTS FOR 'atlas_ro'@'100.%.%.%';

-- B) Negative tests — run these WHILE CONNECTED AS atlas_ro (not as root).
--    Each MUST fail. If any succeeds, the user is over-privileged: drop and redo.
--
--    -- writes must be denied:
--    --   INSERT INTO `<dopos_DB>`.<any_table> VALUES (...);   -- expect: ERROR 1142
--    --   UPDATE `<dopos_DB>`.<any_table> SET ...;             -- expect: ERROR 1142
--    --   DELETE FROM `<dopos_DB>`.<any_table>;                -- expect: ERROR 1142
--    --   CREATE TABLE `<dopos_DB>`.zzz_probe (id INT);        -- expect: ERROR 1142
--    --   DROP TABLE `<dopos_DB>`.<any_table>;                 -- expect: ERROR 1142
--    -- privilege escalation must be denied:
--    --   GRANT SELECT ON `<dopos_DB>`.* TO 'atlas_ro'@'100.%.%.%';  -- expect: ERROR 1044/1142
--    -- other schemas must be invisible:
--    --   SELECT * FROM mysql.user LIMIT 1;                      -- expect: ERROR 1142 (no access)
--
--    -- reads that MUST succeed (proves the mirror will work):
--    --   SELECT COUNT(*) FROM `<dopos_DB>`.<some_table>;      -- expect: a number
--    --   SHOW TABLES IN `<dopos_DB>`;                          -- expect: the table list

-- =============================================================================
-- ROLLBACK (remove the user entirely):
--   DROP USER 'atlas_ro'@'100.%.%.%';
--   FLUSH PRIVILEGES;
-- =============================================================================
