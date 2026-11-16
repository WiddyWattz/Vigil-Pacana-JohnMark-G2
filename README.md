# Vigil — Account Feature (IM2)

**Vigil** is a GPS-based motorcycle speed monitoring system. This repository is the
**IM2 (Information Management 2) web application** for Vigil's **Account Feature**:
registration, login/logout, role-based dashboards, and user profiles.

- **Author:** John Mark P. Pacaña — Section G2
- **Stack:** Python Django (backend + templates), PostgreSQL on Supabase, Django built-in authentication
- **Design:** black & white, based on the provided login and dashboard templates

---

## Features

| Requirement | Where it lives |
|---|---|
| Registration with validation (required fields, email format, unique username & email, password confirmation, strong passwords) | `accounts/forms.py` → `RegistrationForm`, `accounts/views.py` → `register` |
| Password hashing (PBKDF2-SHA256, never plain text) | `user.set_password()` in `RegistrationForm.save()` |
| Login with error message for invalid credentials | `accounts/views.py` → `LoginView` (Django's built-in) |
| Logout that ends the session (POST only) | `accounts/views.py` → `LogoutView` |
| Two roles: **Administrator** and **Rider** | `accounts/models.py` → `User.Role` |
| Redirect to the right dashboard after login | `dashboards/views.py` → `home` |
| Backend role enforcement (403 for the wrong role, login redirect for guests) | `accounts/decorators.py` → `role_required` |
| Rider dashboard | `templates/dashboards/user_dashboard.html` |
| Admin dashboard + user management (search, change role, activate/deactivate) | `templates/dashboards/admin_dashboard.html`, `manage_users.html` |
| Profile view & edit (name, username, email, contact number, photo, speed limit) | `accounts/views.py` → `profile` |
| Change password | `accounts/views.py` → `change_password` |
| CSRF protection on every form | `{% csrf_token %}` + `CsrfViewMiddleware` |
| Secrets in `.env` | `config/settings.py`, `.env.example` |

### Roles

| Role | How you get it | Can access |
|---|---|---|
| **Rider** | Every new registration | Rider dashboard, own profile |
| **Administrator** | `createsuperuser`, or promoted by another admin | Admin dashboard, Manage Users, own profile, Django admin (if staff) |

A rider who types `/dashboard/admin/` gets **403 Forbidden**, and an admin who types
`/dashboard/rider/` gets 403 too. Guests are redirected to the login page. The checks run on
the server (`role_required`), so hiding a link is not the only protection.

---

## Project structure

```
vigil/
├── config/                 # Django project settings & root URLs
│   ├── settings.py         # reads SECRET_KEY / DATABASE_URL from .env
│   └── urls.py
├── accounts/               # users, roles, registration, login/logout, profile
│   ├── models.py           # custom User (role, contact_number, profile_photo, speed_limit) + LoginActivity
│   ├── forms.py            # server-side validation
│   ├── views.py
│   ├── decorators.py       # @role_required
│   ├── signals.py          # records each login for the dashboard charts
│   └── tests.py
├── dashboards/             # role-specific dashboards + admin user management
│   ├── views.py
│   └── tests.py
├── templates/
│   ├── base.html, base_dashboard.html, 403.html, 404.html
│   ├── accounts/           # login, register, profile, change_password
│   ├── dashboards/         # user_dashboard, admin_dashboard, manage_users
│   └── partials/           # icons, messages, form field, avatar, chart, ring
├── static/
│   ├── css/                # common.css, auth.css, dashboard.css
│   ├── js/main.js          # toasts, mobile menu, photo preview
│   └── img/
├── requirements.txt
├── .env.example
└── manage.py
```

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/WiddyWattz/Vigil-Pacana-JohnMark-G2.git
cd Vigil-Pacana-JohnMark-G2
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Create the Supabase database

1. Create a project at [supabase.com](https://supabase.com) and set a database password.
2. Click **Connect** → **Connection string** → **URI**, and choose **Session pooler**
   (the "Direct connection" host only works on IPv6 networks).
3. Copy the string and replace `[YOUR-PASSWORD]` with your database password. If the password has
   special characters (`? @ : / # + ,` …), URL-encode them, e.g. `?` → `%3F`, `+` → `%2B`, `,` → `%2C`.

### 3. Configure `.env`

```bash
cp .env.example .env
```

Fill in `SECRET_KEY` (generate one with the command in `.env.example`) and `DATABASE_URL`.
**Never commit `.env`** — it's already in `.gitignore`.

### 4. Create the tables and an administrator

```bash
python manage.py migrate
python manage.py createsuperuser     # this account is automatically an Administrator
python manage.py runserver
```

Open http://127.0.0.1:8000/ — you'll land on the login page.

### 5. Run the tests

```bash
python manage.py test --keepdb
```

Django runs the tests in a separate `test_postgres` database on the same server, and each test is
rolled back, so your real data is never touched. `--keepdb` keeps that test database between runs:
Supabase's connection pooler holds connections open, which otherwise blocks Django from deleting it.

---

## How the key parts work (for the defense)

- **Custom user model** (`accounts/models.py`): extends Django's `AbstractUser`, so we keep
  Django's username, password hashing, and sessions, and only *add* `role`, `contact_number`,
  `profile_photo`, and `speed_limit`. `email` is made `unique=True`.
- **Password hashing**: `set_password()` stores `pbkdf2_sha256$<iterations>$<salt>$<hash>`.
  The real password can't be read back; login uses `check_password()` to compare.
- **Role redirect**: after login Django goes to `LOGIN_REDIRECT_URL` (`dashboards:home`),
  which looks at `request.user.role` and redirects to the admin or rider dashboard.
- **`@role_required(...)`** (`accounts/decorators.py`): wraps `@login_required` (guests → login page)
  and raises `PermissionDenied` (→ `403.html`) if the role doesn't match.
- **Profile security**: the profile URL has no user ID; the form always edits `request.user`, so
  nobody can open someone else's profile. `role` is not in the profile form, so users can't promote themselves.
- **Dashboard data is real**: counts come from the database, the weekly chart counts rows in
  `LoginActivity` (saved by the `user_logged_in` signal) and new registrations per day.
