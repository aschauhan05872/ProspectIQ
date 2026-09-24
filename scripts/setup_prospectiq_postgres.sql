-- ProspectIQ PostgreSQL bootstrap for local validation (WS6.1)
-- Run as a PostgreSQL superuser (e.g. postgres) on your local instance.
-- Does NOT change ProspectIQ application credentials — matches docker-compose.yml.

CREATE ROLE prospectiq WITH LOGIN PASSWORD 'prospectiq';

CREATE DATABASE prospectiq OWNER prospectiq;
CREATE DATABASE prospectiq_test OWNER prospectiq;

GRANT ALL PRIVILEGES ON DATABASE prospectiq TO prospectiq;
GRANT ALL PRIVILEGES ON DATABASE prospectiq_test TO prospectiq;

-- After running this script:
--   cd backend
--   $env:PROSPECTIQ_DATABASE_URL="postgresql+asyncpg://prospectiq:prospectiq@localhost:5432/prospectiq"
--   $env:PROSPECTIQ_TEST_DATABASE_URL="postgresql+asyncpg://prospectiq:prospectiq@localhost:5432/prospectiq_test"
--   alembic upgrade head
--   pytest -m integration
