-- Runs once, only when the Postgres data volume is first initialized.
-- Twenty's "default" DB is created by POSTGRES_DB; this adds n8n's database.
SELECT 'CREATE DATABASE n8n'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'n8n')\gexec

-- Stalwart mail server database
SELECT 'CREATE DATABASE stalwart'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'stalwart')\gexec
