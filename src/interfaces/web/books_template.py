"""HTML rendering for the local web UI's Books page.

Split out from `templates.py` to keep that file under the project's
500-line limit; shares the same dark-theme stylesheet via `_page`.
"""

from __future__ import annotations

from src.interfaces.web.books_service import BooksPageView, ClaimView
from src.interfaces.web.templates import _page

_VALIDATION_LABELS_RU = {
    "pending": "в очереди",
    "accepted": "принято",
    "rejected": "отклонено",
    "unknown": "неизвестно",
}


def _book_row(title: str, author: str, category: str | None, validation_status: str) -> str:
    css_class = {"accepted": "pos", "rejected": "neg"}.get(validation_status, "muted")
    label = _VALIDATION_LABELS_RU.get(validation_status, validation_status)
    return (
        f"<tr><td>{title}</td><td class='muted'>{author}</td>"
        f"<td class='muted'>{category or '-'}</td>"
        f"<td class='{css_class}'>{label}</td></tr>"
    )


def _claim_item(claim: ClaimView) -> str:
    topic_tag = f'<span class="tag">{claim.topic}</span>' if claim.topic else ""
    return (
        f'<div class="row"><span>{claim.statement}</span>'
        f'<span>{topic_tag}<span class="value">{claim.confidence:.0%}</span></span></div>'
    )


def render_books_html(view: BooksPageView) -> str:
    """Render the Books page.

    Args:
        view: The current `BooksPageView`.

    Returns:
        A complete HTML document.
    """
    book_rows = (
        "".join(
            _book_row(book.title, book.author, book.category, book.validation_status)
            for book in view.books
        )
        or '<tr><td class="muted" colspan="4">Книги ещё не обработаны</td></tr>'
    )

    accepted_items = (
        "".join(_claim_item(claim) for claim in view.accepted_claims)
        or '<div class="muted">Подтверждённых гипотез пока нет</div>'
    )
    rejected_items = (
        "".join(_claim_item(claim) for claim in view.rejected_claims)
        or '<div class="muted">Отклонённых гипотез пока нет</div>'
    )

    return _page(
        "Книги",
        f"""
<h1>Книги и гипотезы</h1>
<div class="nav"><a href="/">← Панель</a> · <a href="/settings">Настройки →</a></div>

<div class="grid">
  <div class="card">
    <h2>Обработка</h2>
    <div class="row"><span class="label">Книги обработаны</span>
      <span class="value">{view.processed} / {view.discovered}</span></div>
    <div class="row"><span class="label">Папка</span>
      <span class="value muted">{view.watched_directory}</span></div>
  </div>

  <div class="card">
    <h2>Гипотезы (заявления из книг)</h2>
    <div class="row"><span class="label">В очереди на проверку</span>
      <span class="value">{view.claim_counts.get("pending", 0)}</span></div>
    <div class="row"><span class="label">Подтверждено</span>
      <span class="value pos">{view.claim_counts.get("accepted", 0)}</span></div>
    <div class="row"><span class="label">Отклонено</span>
      <span class="value neg">{view.claim_counts.get("rejected", 0)}</span></div>
  </div>
</div>

<div class="card">
  <h2>Подтверждённые гипотезы</h2>
  {accepted_items}
</div>

<div class="card">
  <h2>Отклонённые гипотезы</h2>
  {rejected_items}
</div>

<div class="card">
  <h2>Обработанные книги</h2>
  <table><tr><th>Название</th><th>Автор</th><th>Категория</th><th>Статус</th></tr>{book_rows}</table>
</div>
""",
    )
