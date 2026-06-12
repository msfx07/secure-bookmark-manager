# Secure Bookmark Manager

![Python](https://img.shields.io/badge/python-3.11-blue?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/flask-3.1.1-lightgrey?logo=flask)
![Docker](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)

A self-hosted, containerised bookmark manager built with Flask. Organise URLs into custom emoji-tagged categories, search across your entire collection, and validate link health — all behind a secure login system with optional Time-based Two-Factor Authentication (TOTP).

**Live site:** [bookmark.sandbox99.cc](https://bookmark.sandbox99.cc/)

---

## Screenshots

<table>
  <tr>
    <td align="center"><a href="screenshot/secure-bookmark-manager-login.png" target="_blank"><img src="screenshot/secure-bookmark-manager-login.png" width="260" alt="Login"/></a><br/><sub>Login</sub></td>
    <td align="center"><a href="screenshot/dashboard-01.png" target="_blank"><img src="screenshot/dashboard-01.png" width="260" alt="Dashboard"/></a><br/><sub>Dashboard</sub></td>
    <td align="center"><a href="screenshot/dashboard-account-settings.png" target="_blank"><img src="screenshot/dashboard-account-settings.png" width="260" alt="Account Settings"/></a><br/><sub>Account Settings</sub></td>
  </tr>
</table>

---

## Features

- **User authentication** — register, login, and logout with Werkzeug-hashed passwords and HIBP breach checking
- **Two-factor authentication** — optional TOTP via Google Authenticator, Authy, or any compatible app
- **Bookmark CRUD** — add, edit, and delete bookmarks with title, URL, category, tags, and auto-scraped metadata
- **Category organisation** — flat single-level categories with custom emoji icons per category
- **Bulk delete** — multi-select bookmarks for batch deletion from the dashboard
- **Tag support** — attach comma-separated tags to any bookmark
- **Full-text search** — search by title, URL, category, or tags in a single query
- **Link validation** — async background health checker flags broken or unreachable URLs
- **Data portability** — export and import bookmarks as standard Netscape HTML bookmark files
- **Dual SQLite databases** — `auth.db` for credentials, `bookmarks.db` for content; persisted via a named Docker volume
- **Bootstrap 5 UI** — responsive two-column dashboard, dark mode toggle, accordion sidebar settings panel

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, Flask 3.1.1, Flask-Login 0.6.3 |
| Security | Werkzeug password hashing, PyOTP (TOTP), HIBP breach API |
| Database | SQLite3 (dual-database architecture) |
| Frontend | Jinja2 templates, Bootstrap 5.3.2, Bootstrap Icons 1.11.3 |
| Server | Gunicorn 23 |
| Container | Docker, Docker Compose |
| Async | aiohttp 3.9.5 (link validator) |

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)

No local Python installation is required.

---

## Quick Start

**1. Clone the repository**

```bash
git clone https://github.com/msfx07/secure-bookmark-manager.git
cd secure-bookmark-manager
```

**2. Configure environment variables**

Create a `.env` file in the project root:

```env
FLASK_ENV=production
SECRET_KEY=replace_this_with_a_long_random_string
```

> **Important:** Use a long, random value for `SECRET_KEY`. Never commit this file — it is already git-ignored.

**3. Build and run**

```bash
docker compose up --build -d
```

**4. Open in your browser**

```
http://localhost:5000
```

> **Account Access Notice:** This application does not include a default admin account or preconfigured login credentials. For security reasons, each user must create an account through the registration page before signing in.

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `SECRET_KEY` | Flask session signing key — **change before deploying** | `dev_fallback_secret` |
| `FLASK_ENV` | Flask environment (`production` or `development`) | `production` |

---

## Data Persistence

Bookmark and user data are stored in SQLite databases at `/app/data/` inside the container. The named Docker volume `bookmark_data` maps to this path, so data survives container restarts and rebuilds.

```bash
# Stop without losing data
docker compose down

# Destroy containers AND wipe all data
docker compose down -v
```

---

## Factory Reset

A host-only reset script is included for wiping all users and bookmarks:

```bash
sudo ./reset_factory.sh
```

This stops the container, removes both databases from the Docker volume, and restarts the application. It requires `sudo` and is excluded from the Docker image via `.dockerignore`.

---

## Project Structure

```
secure-bookmark-manager/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── app.py                    # App factory, LoginManager, DB init, blueprint registration
├── reset_factory.sh          # Host-only factory reset (not in Docker image)
├── .dockerignore
├── .env                      # Local secrets (git-ignored)
├── data/                     # Local mirror of Docker volume (git-ignored)
├── models/
│   ├── auth_db.py            # User model, password hashing, TOTP helpers
│   └── bookmark_db.py        # Bookmark CRUD, category list/rename/emoji, search, validation
├── routes/
│   ├── auth.py               # Register, login, logout, 2FA setup/verify/disable, change-password, delete-account
│   └── bookmarks.py          # Dashboard, CRUD, export, import, bulk-delete, category icon, link validate
├── services/
│   └── validator.py          # Async link health checker — background daemon + per-user trigger
├── templates/
│   ├── base.html             # Bootstrap layout, navbar, dark mode, flash messages, footer
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html        # Two-column layout, category sidebar, bookmark grid, bulk select
│   ├── edit.html
│   ├── about.html
│   ├── privacy.html
│   ├── disclaimer.html
│   ├── 2fa_setup.html        # QR code + manual key + confirmation form
│   └── 2fa_verify.html       # Login checkpoint
└── static/
    └── css/custom.css
```

---

## Two-Factor Authentication

2FA is optional and per-user. To enable it:

1. Log in and open the **Security Setup** panel in the dashboard sidebar.
2. Click **Enable 2FA** and scan the QR code with your authenticator app.
3. Enter the 6-digit code to confirm — 2FA is now active.

On every subsequent login you will be prompted for a TOTP code before reaching the dashboard. To disable, click **Disable 2FA** in the same sidebar panel.

---

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

---

## License

MIT
