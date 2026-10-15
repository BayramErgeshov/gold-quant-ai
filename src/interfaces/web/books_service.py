"""Data assembly for the local web UI's Books page.

Per the "Books" production requirement: "Show processing progress inside
the interface. Show validated hypotheses. Show rejected hypotheses."
`BookClaim` (per BOOK_RAG.md: "Every important statement becomes a
claim... No claim becomes production knowledge automatically") is the
book-derived hypothesis: it starts `pending` and only the Historical
Research Engine's statistical validation ever moves it to
`accepted`/`rejected` -- this module only ever displays whatever that
validation has actually produced so far, never a fabricated count.

Deliberately separate from `DashboardStatus.learning_progress`
(`ImprovementProposal`, the trading-*strategy* self-improvement queue) --
book claims and strategy proposals are different hypothesis pipelines
with different sources of evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from src.engines.book_engine.document_extraction import SUPPORTED_EXTENSIONS
from src.models.book import VALIDATION_STATUSES
from src.repositories.book_claim_repository import BookClaimRepository
from src.repositories.book_repository import BookRepository
from src.repositories.runtime_settings_repository import RuntimeSettingsRepository

_DEFAULT_WATCHED_DIRECTORY = Path("books")
_MAX_BOOKS_LISTED = 200
_MAX_CLAIMS_SAMPLED = 15


@dataclass(frozen=True, slots=True)
class BookRowView:
    """A single ingested book's processing state.

    Attributes:
        title: Book title.
        author: Book author.
        category: Topic category, if classified.
        validation_status: One of `src.models.book.VALIDATION_STATUSES`.
    """

    title: str
    author: str
    category: str | None
    validation_status: str


@dataclass(frozen=True, slots=True)
class ClaimView:
    """A single extracted book claim (hypothesis).

    Attributes:
        statement: The claim text.
        topic: Topic category, if classified.
        confidence: Validation confidence; 0.0 while still `pending`.
    """

    statement: str
    topic: str | None
    confidence: float


@dataclass(frozen=True, slots=True)
class BooksPageView:
    """Everything the Books page needs.

    Attributes:
        processed: Books already ingested (rows in the `books` table).
        discovered: Supported files currently sitting in the watched
            folder, whether processed yet or not.
        watched_directory: The folder actually being polled this cycle
            (honors the "Books Folder" settings override, if set).
        books: Every ingested book, most recently added first.
        claim_counts: Claim/hypothesis counts by validation status --
            every status in `VALIDATION_STATUSES` is always present (0 if
            empty), so the page can show a complete breakdown.
        accepted_claims: A sample of validated (accepted) hypotheses.
        rejected_claims: A sample of rejected hypotheses.
    """

    processed: int = 0
    discovered: int = 0
    watched_directory: str = str(_DEFAULT_WATCHED_DIRECTORY)
    books: list[BookRowView] = field(default_factory=list)
    claim_counts: dict[str, int] = field(
        default_factory=lambda: dict.fromkeys(VALIDATION_STATUSES, 0)
    )
    accepted_claims: list[ClaimView] = field(default_factory=list)
    rejected_claims: list[ClaimView] = field(default_factory=list)


def _count_discovered_books(watched_directory: Path) -> int:
    if not watched_directory.is_dir():
        return 0
    return sum(
        1
        for path in watched_directory.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


async def get_books_page(session: AsyncSession) -> BooksPageView:
    """Assemble the current Books page from persisted data.

    Args:
        session: The active database session.

    Returns:
        The `BooksPageView` for the Books page.
    """
    runtime_settings = await RuntimeSettingsRepository(session).get_or_create_default()
    watched_directory = (
        Path(runtime_settings.books_folder)
        if runtime_settings.books_folder
        else _DEFAULT_WATCHED_DIRECTORY
    )

    books = await BookRepository(session).list_all(limit=_MAX_BOOKS_LISTED)
    claim_repository = BookClaimRepository(session)
    claim_counts = await claim_repository.count_by_status()
    accepted = await claim_repository.list_by_status("accepted", limit=_MAX_CLAIMS_SAMPLED)
    rejected = await claim_repository.list_by_status("rejected", limit=_MAX_CLAIMS_SAMPLED)

    return BooksPageView(
        processed=len(books),
        discovered=_count_discovered_books(watched_directory),
        watched_directory=str(watched_directory),
        books=[
            BookRowView(
                title=book.title,
                author=book.author,
                category=book.category,
                validation_status=book.validation_status,
            )
            for book in books
        ],
        claim_counts=claim_counts,
        accepted_claims=[
            ClaimView(statement=claim.statement, topic=claim.topic, confidence=claim.confidence)
            for claim in accepted
        ],
        rejected_claims=[
            ClaimView(statement=claim.statement, topic=claim.topic, confidence=claim.confidence)
            for claim in rejected
        ],
    )
