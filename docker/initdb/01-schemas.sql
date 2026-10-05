-- Runs once, when the postgres container initialises an empty data directory.
--
-- Django's tables do not move here in Phase 2 - the schema only exists so the
-- service boundary is visible from day one. FastAPI's `telemetry` schema is
-- created by Alembic (see backend/fastapi/alembic/env.py), so it is not here.
CREATE SCHEMA IF NOT EXISTS core;
