# Changelog

All notable changes to the Secure Bookmark Manager project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.3.0] - 2026-08-12

### Added
- **CSRF Protection** — Flask-WTF cross-site request forgery protection on all 15 POST forms
- **Rate Limiting** — Flask-Limiter with 10 req/min on login and 2FA endpoints, 200/day and 60/hour global limits
- **Session Cookie Hardening** — `HttpOnly`, `Secure`, and `SameSite=Lax` attributes enforced
- **Unified Password Policy** — Minimum 14 characters, maximum 64 characters, no spaces (admin and self-service)
- **Enhanced .dockerignore** — Comprehensive exclusions for secrets, IDE files, and dev artifacts

### Changed
- **Default Admin Logging** — No longer prints password to stdout on first run
- **Security Policy** — Updated `SECURITY.md` with CSRF, rate limiting, and password policy documentation

---

## [1.2.0] - 2026-08-11

### Added
- **Consolidated Database** — Merged `auth.db` and `bookmarks.db` into a single `bookmarks.db` file
- **Deploy Script** — New `deploy.sh` for automated setup and deployment
  - Docker/Docker Compose version checks
  - Automatic `.env` generation with secure random secret key
  - SQLite schema initialization
  - Container health verification
- **Default Admin Account** — Created automatically on first run with credentials `admin` / `Secure-Bookmark-Manager`
- **Security Policy** — Added comprehensive `SECURITY.md` documentation
- **Changelog** — Added this `CHANGES.md` file for tracking updates

### Changed
- **Database Architecture** — Moved from dual-database to single consolidated database
  - `users` table now lives in `bookmarks.db`
  - Simplified backup and restore procedures
  - Reduced file management overhead
- **Authentication** — Removed public registration; only administrators can create accounts
- **Environment Variables** — Removed `AUTH_DB_PATH` (no longer needed)
  - Updated `.env.example` to reflect consolidated database
- **Documentation** — Updated README.md to reflect database consolidation

### Removed
- **Registration Page** — `/register` route and `register.html` template removed
- **Factory Reset Script** — `reset_factory.sh` removed (no longer needed)
- **Separate Auth Database** — `auth.db` no longer used
  - Old `AUTH_DB_PATH` environment variable removed
  - Migration path provided for existing deployments

### Fixed
- **Schema Consistency** — Ensured all tables are properly initialized in consolidated database
- **Migration Handling** — Improved idempotent migrations for both users and bookmarks tables

---

## [1.1.0] - 2026-08-01

### Added
- **HIBP Breach Checking** — Passwords checked against Have I Been Pwned database
- **Link Validation** — Background health checker for broken URLs
- **Category Emoji Support** — Custom emoji icons for bookmark categories
- **Bulk Delete** — Multi-select bookmarks for batch deletion
- **Tag Support** — Comma-separated tags for bookmark organization
- **Full-Text Search** — Search across title, URL, category, and tags

### Changed
- **UI Improvements** — Enhanced Bootstrap 5 dashboard with dark mode
- **Performance** — Optimized database queries for large bookmark collections
- **Error Handling** — Improved error messages and user feedback

### Fixed
- **XSS Prevention** — Enhanced URL sanitization filter
- **Session Security** — Improved cookie handling and session management

---

## [1.0.0] - 2026-07-15

### Added
- **User Authentication** — Register, login, and logout functionality
- **Two-Factor Authentication** — TOTP support via Google Authenticator
- **Bookmark CRUD** — Create, read, update, and delete bookmarks
- **Category Organization** — Flat single-level categories
- **Docker Support** — Containerized deployment with Docker Compose
- **SQLite Database** — Persistent storage for users and bookmarks
- **Responsive UI** — Bootstrap 5 interface with mobile support

### Security
- **Password Hashing** — Werkzeug PBKDF2-SHA256 with automatic salting
- **CSRF Protection** — Flask-WTF cross-site request forgery prevention
- **Session Signing** — Cryptographic session cookies
- **SQL Injection Prevention** — Parameterized queries throughout

---

## Migration Guide

### Upgrading from 1.1.x to 1.2.0

If you have an existing deployment with separate `auth.db` and `bookmarks.db` files:

1. **Backup your data**
   ```bash
   docker cp bookmark-manager:/app/data/auth.db ./backup/
   docker cp bookmark-manager:/app/data/bookmarks.db ./backup/
   ```

2. **Run the deployment script**
   ```bash
   ./deploy.sh
   ```

3. **The script will automatically:**
   - Create the consolidated database
   - Migrate user data from `auth.db` to `bookmarks.db`
   - Initialize all required tables

4. **Verify the migration**
   ```bash
   sqlite3 ./data/bookmarks.db ".tables"
   # Should show: users, bookmarks, category_meta
   ```

5. **Remove old database (optional)**
   ```bash
   docker exec bookmark-manager rm /app/data/auth.db
   ```

---

## Upcoming Features

### Planned for 1.3.0
- **Import/Export Enhancement** — Support for more bookmark formats
- **Browser Extension** — Chrome/Firefox extension for quick bookmark saving
- **API Endpoints** — RESTful API for programmatic access
- **Multi-User Support** — Shared bookmark collections

### Planned for 1.4.0
- **Search Enhancement** — Full-text search with ranking
- **Archive Support** — Web Archive integration for broken links
- **Tags Auto-Suggestion** — AI-powered tag recommendations
- **Mobile App** — Native iOS and Android applications

---

## Version Scheme

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html):

- **MAJOR** (X.0.0) — Incompatible API changes
- **MINOR** (0.X.0) — Backwards-compatible new features
- **PATCH** (0.0.X) — Backwards-compatible bug fixes

---

## Contributors

- **Jose Mendez** — Original author and maintainer
- **AI Collaboration** — Development assistance and code review

---

## License

This changelog is part of the Secure Bookmark Manager project, licensed under the MIT License.
