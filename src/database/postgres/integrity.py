"""Database schema integrity checks.

Per DATA_QUALITY_STANDARD.md ("Every dataset verified by ... Version ...
Integrity Hash") and DATABASE.md ("Integrity Check"). Verifies the live
database's applied migration matches the latest migration shipped in this
checkout, so the platform never silently operates against a stale or
ahead-of-code schema.
"""

from __future__ import annotations

from dataclasses import dataclass

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config.yaml_loader import PROJECT_ROOT

_ALEMBIC_INI_PATH = PROJECT_ROOT / "alembic.ini"
_MIGRATIONS_PATH = PROJECT_ROOT / "src" / "database" / "migrations"


@dataclass(frozen=True, slots=True)
class MigrationIntegrityResult:
    """Outcome of comparing the database schema version against local code.

    Attributes:
        healthy: True if the database is on the latest known migration.
        database_revision: The revision currently applied to the database,
            or None if it could not be determined.
        expected_revision: The latest migration revision available locally.
        detail: Human-readable explanation of the result.
    """

    healthy: bool
    database_revision: str | None
    expected_revision: str | None
    detail: str


def get_latest_local_revision() -> str | None:
    """Read the latest migration revision from the local migrations folder.

    Returns:
        The head revision id, or None if no migrations exist yet.
    """
    config = Config(str(_ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(_MIGRATIONS_PATH))
    return ScriptDirectory.from_config(config).get_current_head()


async def check_migration_integrity(session: AsyncSession) -> MigrationIntegrityResult:
    """Compare the database's applied migration against the local codebase.

    Args:
        session: An active `AsyncSession`.

    Returns:
        A `MigrationIntegrityResult` describing whether the schema is current.
    """
    expected = get_latest_local_revision()

    try:
        result = await session.execute(text("SELECT version_num FROM alembic_version"))
        database_revision = result.scalar_one_or_none()
    except Exception as exc:  # noqa: BLE001 - any DB failure must be reported, not raised
        return MigrationIntegrityResult(
            healthy=False,
            database_revision=None,
            expected_revision=expected,
            detail=f"{type(exc).__name__}: {exc}",
        )

    healthy = database_revision == expected
    detail = "database schema is current" if healthy else "database schema is out of date"
    return MigrationIntegrityResult(
        healthy=healthy,
        database_revision=database_revision,
        expected_revision=expected,
        detail=detail,
    )
