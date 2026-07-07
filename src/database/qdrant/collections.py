"""Qdrant collection bootstrap.

Creates every collection declared in `config/database.yaml` (`qdrant.collections`)
if it does not already exist. Idempotent: safe to call on every startup, per
DATABASE.md ("Qdrant... Book Embeddings, Research Embeddings, ...").

Collections backed by a configurable embedding provider (currently just
"books", see `src.core.embeddings`) are bootstrapped separately via
`ensure_collection_for_dimension`, since their vector size depends on
whichever model is active at runtime rather than a static config value.
"""

from __future__ import annotations

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, HnswConfigDiff, VectorParams

from src.common.logging import get_logger
from src.settings import Settings

logger = get_logger(__name__)

_DISTANCE_BY_NAME: dict[str, Distance] = {
    "Cosine": Distance.COSINE,
    "Euclid": Distance.EUCLID,
    "Dot": Distance.DOT,
}

# Qdrant's own recommended defaults for balanced recall/speed. Exposed as
# parameters (rather than only ever using the client's implicit defaults)
# so index quality can be deliberately tuned once real query latency/recall
# data exists (OBSERVABILITY_AND_MONITORING.md "Qdrant Metrics": "Search
# Latency... Index Quality").
_DEFAULT_HNSW_M = 16
_DEFAULT_HNSW_EF_CONSTRUCT = 200


def _default_hnsw_config() -> HnswConfigDiff:
    return HnswConfigDiff(m=_DEFAULT_HNSW_M, ef_construct=_DEFAULT_HNSW_EF_CONSTRUCT)


class CollectionDimensionMismatchError(RuntimeError):
    """An existing Qdrant collection's vector size does not match the active provider.

    Raised instead of silently proceeding: mixing embeddings from
    differently-sized models in one collection would silently corrupt
    similarity search, and switching embedding models requires deliberately
    re-embedding existing content, not an automatic migration.
    """


async def ensure_collection_for_dimension(
    client: AsyncQdrantClient,
    name: str,
    *,
    dimension: int,
    distance: Distance = Distance.COSINE,
    hnsw_config: HnswConfigDiff | None = None,
) -> bool:
    """Create a collection sized for the given dimension, or validate it matches.

    Args:
        client: An active `AsyncQdrantClient`.
        name: Collection name.
        dimension: Expected vector size (from the active embedding provider).
        distance: Similarity metric to use if the collection is created.
        hnsw_config: HNSW index parameters; defaults to Qdrant's own
            recommended `m`/`ef_construct` values.

    Returns:
        True if the collection was newly created, False if it already
        existed with a matching dimension.

    Raises:
        CollectionDimensionMismatchError: If the collection already exists
            with a different vector size than `dimension`.
    """
    existing_names = {
        collection.name for collection in (await client.get_collections()).collections
    }

    if name not in existing_names:
        await client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dimension, distance=distance),
            hnsw_config=hnsw_config or _default_hnsw_config(),
        )
        logger.info("qdrant_collection_created", collection=name, vector_size=dimension)
        return True

    collection_info = await client.get_collection(name)
    existing_size = collection_info.config.params.vectors.size  # type: ignore[union-attr]
    if existing_size != dimension:
        raise CollectionDimensionMismatchError(
            f"Qdrant collection {name!r} has vector size {existing_size}, "
            f"but the active embedding provider produces {dimension}-dim vectors. "
            "Re-embedding existing content into a new collection is required "
            "before switching embedding models."
        )
    return False


async def ensure_collections_exist(client: AsyncQdrantClient, settings: Settings) -> list[str]:
    """Create every configured Qdrant collection that does not already exist.

    Args:
        client: An active `AsyncQdrantClient`.
        settings: Application settings, providing collection definitions
            from `config/database.yaml`.

    Returns:
        Names of the collections that were newly created.
    """
    existing = {collection.name for collection in (await client.get_collections()).collections}
    created: list[str] = []

    for name, spec in settings.platform.database.qdrant.get("collections", {}).items():
        if name in existing:
            continue
        await client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(
                size=spec["vector_size"],
                distance=_DISTANCE_BY_NAME[spec["distance"]],
            ),
            hnsw_config=_default_hnsw_config(),
        )
        created.append(name)
        logger.info("qdrant_collection_created", collection=name, vector_size=spec["vector_size"])

    return created
