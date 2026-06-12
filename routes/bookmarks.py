import ipaddress
import socket
import requests
from collections import defaultdict
from html import escape
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from flask import Blueprint, render_template, redirect, url_for, request, flash, Response
from flask_login import login_required, current_user
from models.bookmark_db import (
    add_bookmark, get_bookmark, get_bookmarks,
    update_bookmark, delete_bookmark, log_bookmark_access,
    get_folders, search_bookmarks,
    get_bookmark_urls, import_bookmarks_batch,
    rename_user_category,
    bulk_delete_bookmarks,
    get_category_emoji_map, update_category_emoji,
)
from services.validator import trigger_user_validation

bookmarks = Blueprint("bookmarks", __name__)

_SCRAPER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

_MAX_IMPORT_BYTES = 2 * 1024 * 1024  # 2 MB
_MAX_SCRAPER_REDIRECTS = 5

# Server-side allowlist for category icons — must stay in sync with the
# <select id="ci-emoji"> options in dashboard.html. Any value outside this
# set is rejected and the default folder icon is stored instead.
_ALLOWED_CATEGORY_EMOJIS = frozenset({
    "📁", "💻", "🖥️", "📱", "🛠️", "🚀", "🤖", "🎮", "🎬", "🎵",
    "🎨", "📚", "🔍", "📰", "💼", "🏠", "✈️", "🍕", "💡", "⭐",
    "🎯", "💰", "🛒", "🔖", "⚓",
})


def _is_safe_url(url: str) -> bool:
    """
    Return True only when the URL is safe to store and fetch:
    - scheme must be http or https
    - hostname must resolve exclusively to public IPs (blocks RFC-1918,
      loopback 127.x, link-local 169.254.x including cloud metadata endpoints,
      and other reserved ranges)
    Fails closed: any resolution error returns False.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        for _family, _type, _proto, _canon, sockaddr in socket.getaddrinfo(hostname, None):
            ip = ipaddress.ip_address(sockaddr[0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast):
                return False
        return True
    except Exception:
        return False


def _scrape_metadata(url):
    """
    Fetch url and extract <title> and <meta description> / og:description.
    Returns (title, description) — either value is None when absent or on failure.
    Never raises; network errors are swallowed per the skill spec.

    Redirects are followed manually so every hop is validated through
    _is_safe_url() before the next request is made. This prevents SSRF via
    an attacker-controlled server issuing a redirect to a private/internal IP
    after the initial URL passes the safety check.
    """
    if not _is_safe_url(url):
        return None, None
    try:
        current_url = url
        response = None
        for _ in range(_MAX_SCRAPER_REDIRECTS + 1):
            response = requests.get(
                current_url,
                timeout=3.0,
                headers=_SCRAPER_HEADERS,
                allow_redirects=False,
            )
            if response.is_redirect:
                location = response.headers.get("Location", "").strip()
                next_url = urljoin(current_url, location)
                if not _is_safe_url(next_url):
                    return None, None
                current_url = next_url
            else:
                break
        else:
            return None, None  # redirect limit exceeded

        soup = BeautifulSoup(response.text, "html.parser")

        # Title: extract and truncate to 100 chars
        scraped_title = None
        if soup.title and soup.title.string:
            scraped_title = soup.title.string.strip()[:100]

        # Description: standard meta first, og:description as fallback
        scraped_desc = None
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            scraped_desc = meta["content"].strip()
        else:
            og = soup.find("meta", attrs={"property": "og:description"})
            if og and og.get("content"):
                scraped_desc = og["content"].strip()

        return scraped_title, scraped_desc

    except requests.RequestException:
        return None, None


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@bookmarks.route("/")
@login_required
def dashboard():
    user_id       = current_user.id
    active_folder = request.args.get("folder", "").strip()
    active_search = request.args.get("search", "").strip()

    if active_search:
        bookmark_list = search_bookmarks(user_id, active_search)
    elif active_folder:
        bookmark_list = get_bookmarks(user_id, folder=active_folder)
    else:
        bookmark_list = get_bookmarks(user_id)

    return render_template(
        "dashboard.html",
        bookmarks=bookmark_list,
        folders=get_folders(user_id),
        active_folder=active_folder,
        active_search=active_search,
        emoji_map=get_category_emoji_map(user_id),
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@bookmarks.route("/add", methods=["POST"])
@login_required
def add():
    title       = request.form.get("title",       "").strip()
    url         = request.form.get("url",         "").strip()
    folder      = request.form.get("folder",      "").strip() or "Uncategorized"
    tags        = request.form.get("tags",        "").strip()
    description = request.form.get("description", "").strip()

    if not url:
        flash("URL is required.", "danger")
        return redirect(url_for("bookmarks.dashboard"))

    if not _is_safe_url(url):
        flash("Invalid URL. Only public http:// and https:// addresses are accepted.", "danger")
        return redirect(url_for("bookmarks.dashboard"))

    # Scrape once if either auto-fillable field was left blank
    if not title or not description:
        scraped_title, scraped_desc = _scrape_metadata(url)
        if not title:
            # Domain name as guaranteed fallback so title is never empty
            title = scraped_title or urlparse(url).netloc
        if not description:
            description = scraped_desc or ""

    add_bookmark(current_user.id, title, url, folder, tags, description)
    flash(f'"{title}" added to {folder}.', "success")
    return redirect(url_for("bookmarks.dashboard", folder=folder))


@bookmarks.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit(id):
    bookmark = get_bookmark(id, current_user.id)
    if not bookmark:
        flash("Bookmark not found.", "danger")
        return redirect(url_for("bookmarks.dashboard"))

    if request.method == "POST":
        title       = request.form.get("title",       "").strip()
        url         = request.form.get("url",         "").strip()
        folder      = request.form.get("folder",      "").strip() or "Uncategorized"
        tags        = request.form.get("tags",        "").strip()
        description = request.form.get("description", "").strip()

        if not title or not url:
            flash("Title and URL are required.", "danger")
            return render_template("edit.html", bookmark=bookmark)

        if not _is_safe_url(url):
            flash("Invalid URL. Only public http:// and https:// addresses are accepted.", "danger")
            return render_template("edit.html", bookmark=bookmark)

        update_bookmark(id, current_user.id, title, url, description, folder, tags)
        flash(f'"{title}" updated.', "success")
        return redirect(url_for("bookmarks.dashboard", folder=folder))

    return render_template("edit.html", bookmark=bookmark)


@bookmarks.route("/click/<int:id>")
@login_required
def click(id):
    bookmark = get_bookmark(id, current_user.id)
    if not bookmark:
        flash("Bookmark not found.", "danger")
        return redirect(url_for("bookmarks.dashboard"))
    url = bookmark["url"]
    if urlparse(url).scheme not in ("http", "https"):
        flash("Bookmark has an invalid URL and cannot be opened.", "warning")
        return redirect(url_for("bookmarks.dashboard"))
    log_bookmark_access(id)
    return redirect(url)


@bookmarks.route("/delete/<int:id>", methods=["POST"])
@login_required
def delete(id):
    bookmark = get_bookmark(id, current_user.id)
    if not bookmark:
        flash("Bookmark not found.", "danger")
        return redirect(url_for("bookmarks.dashboard"))

    folder = bookmark.get("folder", "")
    delete_bookmark(id, current_user.id)
    flash(f'"{bookmark["title"]}" deleted.', "success")
    return redirect(url_for("bookmarks.dashboard", folder=folder))


# ---------------------------------------------------------------------------
# Data portability
# ---------------------------------------------------------------------------

@bookmarks.route("/export")
@login_required
def export():
    all_bookmarks = get_bookmarks(current_user.id)

    # Group by folder, preserving the order bookmarks were created
    by_folder = defaultdict(list)
    for bm in all_bookmarks:
        by_folder[bm.get("folder") or "Uncategorized"].append(bm)

    lines = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        "<TITLE>Bookmarks</TITLE>",
        "<H1>Bookmarks</H1>",
        "<DL><p>",
    ]

    for folder_name, bms in by_folder.items():
        lines.append(f"    <DT><H3>{escape(folder_name)}</H3>")
        lines.append("    <DL><p>")
        for bm in bms:
            tags = bm.get("tags") or ""
            lines.append(
                f'        <DT><A HREF="{escape(bm["url"])}" TAGS="{escape(tags)}">'
                f"{escape(bm['title'])}</A>"
            )
        lines.append("    </DL><p>")

    lines.append("</DL><p>")

    return Response(
        "\n".join(lines),
        mimetype="text/html",
        headers={"Content-Disposition": "attachment; filename=bookmarks_backup.html"},
    )


@bookmarks.route("/import", methods=["POST"])
@login_required
def import_bookmarks():
    file = request.files.get("file")
    if not file or not file.filename:
        flash("No file selected.", "danger")
        return redirect(url_for("bookmarks.dashboard"))

    content = file.read()
    if len(content) > _MAX_IMPORT_BYTES:
        flash("File too large. Maximum upload size is 2 MB.", "danger")
        return redirect(url_for("bookmarks.dashboard"))

    soup = BeautifulSoup(content, "html.parser")

    # Load existing URLs into a set to detect duplicates in O(1)
    existing_urls = get_bookmark_urls(current_user.id)

    to_import = []
    skipped   = 0

    for anchor in soup.find_all("a"):
        href = (anchor.get("href") or "").strip()

        # Sanitisation pass — only accept absolute http/https URLs
        if not href.startswith(("http://", "https://")):
            continue

        if href in existing_urls:
            skipped += 1
            continue

        title  = anchor.get_text(strip=True) or urlparse(href).netloc
        tags   = anchor.get("tags") or ""
        h3     = anchor.find_previous("h3")
        folder = h3.get_text(strip=True) if h3 else "Imported"

        to_import.append({
            "title":       title[:100],
            "url":         href,
            "folder":      folder or "Imported",
            "tags":        tags,
            "description": "",
        })
        # Track within-file duplicates so repeated entries aren't double-inserted
        existing_urls.add(href)

    if to_import:
        import_bookmarks_batch(current_user.id, to_import)
        suffix = f" {skipped} duplicate(s) skipped." if skipped else ""
        flash(f"Successfully imported {len(to_import)} bookmark(s).{suffix}", "success")
    else:
        suffix = f" {skipped} duplicate(s) were skipped." if skipped else ""
        flash(f"No new bookmarks found in the uploaded file.{suffix}", "warning")

    return redirect(url_for("bookmarks.dashboard"))


# ---------------------------------------------------------------------------
# Category management
# ---------------------------------------------------------------------------

@bookmarks.route("/rename-category", methods=["POST"])
@login_required
def rename_category():
    old_name = request.form.get("old_category_name", "").strip()
    new_name = request.form.get("new_category_name", "").strip()

    if not new_name:
        flash("Category name cannot be empty.", "warning")
        return redirect(url_for("bookmarks.dashboard"))

    if new_name == old_name:
        flash("New name is identical to the current name. No changes made.", "info")
        return redirect(url_for("bookmarks.dashboard", folder=old_name))

    modified_count = rename_user_category(current_user.id, old_name, new_name)
    flash(
        f'Category successfully migrated. {modified_count} existing '
        f"{'entry' if modified_count == 1 else 'entries'} modified.",
        "success",
    )
    return redirect(url_for("bookmarks.dashboard", folder=new_name))


# ---------------------------------------------------------------------------
# Category icon
# ---------------------------------------------------------------------------

@bookmarks.route("/update-category-icon", methods=["POST"])
@login_required
def update_category_icon():
    category_name = request.form.get("category_name", "").strip()
    emoji         = request.form.get("emoji", "📁").strip()

    if not category_name:
        flash("Category name missing.", "warning")
        return redirect(url_for("bookmarks.dashboard"))

    # Reject anything outside the known icon set — fall back to the default
    # folder icon rather than persisting arbitrary user-supplied text.
    if emoji not in _ALLOWED_CATEGORY_EMOJIS:
        emoji = "📁"

    update_category_emoji(current_user.id, category_name, emoji)
    flash(f'Icon for "{category_name}" updated to {emoji}.', "success")
    return redirect(url_for("bookmarks.dashboard", folder=category_name))


# ---------------------------------------------------------------------------
# Bulk operations
# ---------------------------------------------------------------------------

@bookmarks.route("/bulk-delete", methods=["POST"])
@login_required
def bulk_delete():
    ids_raw = request.form.getlist("bookmark_ids")
    ids = [int(i) for i in ids_raw if i.isdigit()]
    if not ids:
        flash("No bookmarks selected.", "warning")
        return redirect(url_for("bookmarks.dashboard"))
    count = bulk_delete_bookmarks(current_user.id, ids)
    flash(f"{count} bookmark(s) permanently deleted.", "success")
    return redirect(url_for("bookmarks.dashboard"))


# ---------------------------------------------------------------------------
# Link validation
# ---------------------------------------------------------------------------

@bookmarks.route("/validate", methods=["POST"])
@login_required
def validate():
    trigger_user_validation(current_user.id)
    flash(
        "Link validation started. Refresh the page in a moment to see updated health statuses.",
        "info",
    )
    return redirect(url_for("bookmarks.dashboard"))


# ---------------------------------------------------------------------------
# Compliance / informational pages (no login required)
# ---------------------------------------------------------------------------

@bookmarks.route("/about")
def about():
    return render_template("about.html")


@bookmarks.route("/privacy")
def privacy():
    return render_template("privacy.html")


@bookmarks.route("/disclaimer")
def disclaimer():
    return render_template("disclaimer.html")
