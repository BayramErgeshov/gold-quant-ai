-- GOLD QUANT AI — baseline PostgreSQL extensions.
-- Table/schema creation itself is owned by Alembic migrations (Phase 2),
-- per DATABASE.md and DEPLOYMENT.md ("Database Migrations: Automatic, Versioned").

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
