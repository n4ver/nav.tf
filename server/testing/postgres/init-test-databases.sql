-- Test databases on the shared Postgres instance.
-- Runs only on first container init (empty data volume).

CREATE DATABASE cqrs_command_test;
CREATE DATABASE cqrs_query_test;

GRANT ALL PRIVILEGES ON DATABASE cqrs_command_test TO "user";
GRANT ALL PRIVILEGES ON DATABASE cqrs_query_test TO "user";
