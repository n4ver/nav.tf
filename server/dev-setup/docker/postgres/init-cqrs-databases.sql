-- CQRS production databases on the shared Postgres instance.
-- Runs only on first container init (empty data volume).
-- cqrs_command is created automatically as POSTGRES_DB; this script adds cqrs_query.
-- Test databases are created by cqrs/tests/postgres/init-test-databases.sql.

CREATE DATABASE cqrs_query;

GRANT ALL PRIVILEGES ON DATABASE cqrs_query TO "user";
