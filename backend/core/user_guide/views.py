from __future__ import annotations

"""Views for user guide pages."""

import html
import re
from pathlib import Path

from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.safestring import mark_safe
from django.views.generic import TemplateView

from core import models
from core.shared.permissions import RoleRequiredMixin


GUIDE_CONTENT_DIR = Path(__file__).resolve().parent / "content"

GUIDE_MODULES = [
    ("base_files", "Base Files"),
    ("dashboard", "Dashboard"),
    ("application_entry", "Application Entry"),
    ("article_management", "Article Management"),
    ("inventory_planning", "Inventory Planning"),
    ("order_fund_request", "Order & Fund Request"),
    ("seat_allocation", "Seat Allocation"),
    ("sequence_list", "Sequence List"),
    ("token_generation", "Token Generation"),
    ("labels_tags", "Labels & Tags"),
    ("reports", "Reports"),
    ("user_management", "User Management"),
    ("purchase_order", "Purchase Order"),
    ("vendors", "Vendors"),
    ("audit_logs", "Audit Logs"),
    ("user_guide", "User Guide"),
    ("deployment", "Deployment"),
]


def _inline_markdown(value: str) -> str:
    value = html.escape(value)
    value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
    return value


def _render_markdown(markdown_text: str) -> str:
    """Render the small guide markdown subset used by the in-app handbook."""
    lines = markdown_text.splitlines()
    output: list[str] = []
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            output.append("</ul>")
            in_list = False

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            close_list()
            continue

        if line.startswith("# "):
            close_list()
            output.append(f"<h2>{_inline_markdown(line[2:].strip())}</h2>")
        elif line.startswith("## "):
            close_list()
            output.append(f"<h3>{_inline_markdown(line[3:].strip())}</h3>")
        elif line.startswith("### "):
            close_list()
            output.append(f"<h4>{_inline_markdown(line[4:].strip())}</h4>")
        elif line.startswith("- "):
            if not in_list:
                output.append('<ul class="guide-list">')
                in_list = True
            output.append(f"<li>{_inline_markdown(line[2:].strip())}</li>")
        else:
            close_list()
            output.append(f"<p>{_inline_markdown(line)}</p>")

    close_list()
    return mark_safe("\n".join(output))


def _read_guide_file(folder: str, slug: str) -> str:
    path = GUIDE_CONTENT_DIR / folder / f"{slug}.md"
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"# Missing Guide\n\nThe guide file `{folder}/{slug}.md` has not been created yet."


class UserGuideView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    module_key = models.ModuleKeyChoices.USER_GUIDE
    permission_action = "view"
    template_name = "user_guide/user_guide.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        guide_sections = []
        for index, (slug, title) in enumerate(GUIDE_MODULES, start=1):
            guide_sections.append(
                {
                    "number": index,
                    "slug": slug,
                    "title": title,
                    "enduser_html": _render_markdown(_read_guide_file("enduser", slug)),
                    "developer_html": _render_markdown(_read_guide_file("developer", slug)),
                }
            )
        context.update(
            {
                "page_title": "User Guide",
                "guide_sections": guide_sections,
            }
        )
        return context
