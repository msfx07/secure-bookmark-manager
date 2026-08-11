# Security Policy

## Overview

The Secure Bookmark Manager is designed with security as a core principle. This document outlines the security measures implemented and provides guidance for reporting vulnerabilities.

---

## Security Features

### Authentication & Password Security

- **Werkzeug Password Hashing** — All passwords are hashed using PBKDF2-SHA256 with automatic salting
- **HIBP Breach Checking** — Passwords are checked against the Have I Been Pwned database before acceptance
- **Default Admin Account** — Created on first run with credentials `admin` / `Secure-Bookmark-Manager`
- **No Public Registration** — User accounts are managed by administrators only

### Two-Factor Authentication (2FA)

- **TOTP Support** — Time-based One-Time Password compatible with Google Authenticator, Authy, and other TOTP apps
- **Optional Enforcement** — Users can enable/disable 2FA from their account settings
- **Secure Secret Storage** — TOTP secrets are encrypted and stored in the database

### Session Security

- **Cryptographic Session Signing** — Flask sessions are signed with a configurable `SECRET_KEY`
- **Secure Cookie Flags** — Cookies use `HttpOnly`, `Secure`, and `SameSite` attributes
- **Session Timeout** — Sessions expire after inactivity

### Database Security

- **SQLite WAL Mode** — Uses Write-Ahead Logging for better concurrency and crash recovery
- **Parameterized Queries** — All database queries use parameterized statements to prevent SQL injection
- **Consolidated Database** — Single `bookmarks.db` file for easier backup and access control

### Input Validation

- **URL Sanitization** — The `safe_url` Jinja2 filter prevents XSS via `javascript:`, `data:`, and `vbscript:` schemes
- **CSRF Protection** — Flask-WTF provides cross-site request forgery protection
- **Input Length Limits** — Enforced limits on form field lengths

### Container Security

- **Non-Root Execution** — Application runs as a non-root user inside the container
- **Minimal Base Image** — Built on `python:3.11-slim` to reduce attack surface
- **Read-Only Filesystem** — Container filesystem is read-only except for the data volume
- **No Secrets in Image** — Environment variables and secrets are injected at runtime

### Link Validation

- **Background Health Checker** — Async validator detects broken or unreachable URLs
- **HTTPS Enforcement** — Validates that links use secure protocols

---

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

### Do NOT:

- ❌ Open a public GitHub issue for security vulnerabilities
- ❌ Attempt to exploit vulnerabilities on production systems
- ❌ Share vulnerability details publicly before a fix is available

### DO:

- ✅ Email security concerns to: **msfx07@users.noreply.github.com**
- ✅ Include detailed steps to reproduce the vulnerability
- ✅ Allow reasonable time for a fix before public disclosure
- ✅ Provide your contact information for follow-up

### What to Include:

1. **Description** — Clear description of the vulnerability
2. **Steps to Reproduce** — Detailed steps to trigger the issue
3. **Impact Assessment** — Potential impact if exploited
4. **Suggested Fix** — If you have recommendations for fixing

---

## Security Best Practices for Deployment

### Default Credentials

- **Username:** `admin`
- **Password:** `Secure-Bookmark-Manager`

⚠️ **IMPORTANT:** Change the default password immediately after first login!

### Environment Variables

```bash
# Generate a strong secret key
python3 -c "import secrets; print(secrets.token_hex(32))"

# Set in .env file
SECRET_KEY=<your-generated-key>
```

### Docker Compose

```yaml
# Recommended production settings
services:
  web_app:
    restart: unless-stopped
    read_only: true
    tmpfs:
      - /tmp
    security_opt:
      - no-new-privileges:true
```

### Network Security

- Use a reverse proxy (nginx, Traefik) with TLS termination
- Restrict access to port 5000 to localhost only
- Implement rate limiting for login attempts

### Database Backups

```bash
# Backup the database
docker cp bookmark-manager:/app/data/bookmarks.db ./backup/bookmarks-$(date +%Y%m%d).db

# Restore from backup
docker cp ./backup/bookmarks-YYYYMMDD.db bookmark-manager:/app/data/bookmarks.db
```

---

## Data Privacy

- **Local-First** — All data stays on your server; no external services are used
- **No Analytics** — The application does not collect or transmit user analytics
- **No Third-Party Tracking** — No cookies from third-party domains
- **GDPR Compliance** — Users can export and delete their data

---

## Authentication Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Login     │────▶│   2FA       │────▶│  Dashboard  │
│ (admin only)│     │ (optional)  │     │             │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │
       ▼                   ▼
┌─────────────┐     ┌─────────────┐
│ Password    │     │ TOTP Token  │
│ Verification│     │ Verification│
└─────────────┘     └─────────────┘

Default Credentials: admin / Secure-Bookmark-Manager
```

⚠️ **Note:** Public registration has been removed. Only administrators can create new user accounts.

---

## Version History

| Version | Security Updates |
|---------|------------------|
| 1.0.0 | Initial release with password hashing, 2FA, CSRF protection |
| 1.1.0 | Added HIBP breach checking, consolidated database |
| 1.2.0 | Enhanced URL sanitization, improved session security, default admin account |

---

## License

This security policy is part of the Secure Bookmark Manager project, licensed under the MIT License.
