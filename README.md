# Vigil — GPS Speed Monitoring for Riders (IM2)

**Vigil** is a GPS-based motorcycle speed monitoring system. Riders record their trips, get a sound
and vibration alert when they go over their own speed limit, and review their riding history.
This repository is the **IM2 (Information Management 2) web application**:

- **Project Development 1 – Account Feature:** registration, login/logout, role-based dashboards, user profiles
- **Project Development 2 – Core Feature: Trip Tracking & History** (vertical slice: models → views → templates)

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

## Core feature: Trip Tracking & History

The main thing Vigil exists to do: **watch a rider's speed during a trip, warn them when they go over
their limit, and keep a history of every ride.**

### User flow (Rider)

1. Log in → **Start Trip** (sidebar or dashboard button).
2. Name the trip and choose **Device GPS** (phone) or **Demo (simulated GPS)** (laptop demo).
   The trip copies the rider's speed limit from their profile.
3. On the tracking page press **Start tracking**. The browser's Geolocation API reports position and
   speed; a live speedometer shows the current speed. Above the limit the card turns white, a banner
   flashes, and the phone **beeps and vibrates**.
4. Every 3 seconds the readings are sent to Django, validated, and saved. The **server** decides which
   readings become **speed alerts** (one at most every 10 s).
5. **End & save trip** → the server calculates distance, duration, and average/top speed, then opens the
   trip's detail page (speed chart, route outline, alerts).
6. **Trip History** lists every trip (search, status filter, totals). The rider can **edit** a trip's name
   and notes or **delete** it.

### Roles

| Role | In the trip feature |
|---|---|
| **Rider** | Start, track and end trips; view, edit and delete **own** trips only |
| **Administrator** | View **all** riders' trips (filter by rider) and delete any trip; cannot start trips or edit a rider's notes |

### CRUD

| Operation | Where | Who |
|---|---|---|
| Create | Start Trip form → tracking page (Trip, SpeedReadings, SpeedAlerts) | Rider |
| Read | Trip History list, trip detail page, dashboards | Rider (own), Administrator (all) |
| Update | Trip detail → **Edit** (name, notes); ending a trip updates its summary | Rider (own) |
| Delete | Trip detail → **Delete** (confirmation page) | Rider (own), Administrator (any) |

### Data model

```
User 1 ──< Trip 1 ──< SpeedReading 1 ── 0..1 SpeedAlert
                 1 ──< SpeedAlert
```

| Model | Key fields | Relationships |
|---|---|---|
| `Trip` | title, notes, status, source, speed_limit, started_at, ended_at, distance_km, duration_seconds, avg_speed_kmh, max_speed_kmh | ForeignKey → User (`rider`) |
| `SpeedReading` | recorded_at, latitude, longitude, speed_kmh, accuracy_m | ForeignKey → Trip |
| `SpeedAlert` | triggered_at, speed_kmh, speed_limit | ForeignKey → Trip, OneToOne → SpeedReading |

### Business rules and validation

- A rider can have only **one trip in progress** (form check + database `UniqueConstraint`).
- Trip name is required, 3–80 characters. Notes can be up to 500 characters.
- Each GPS reading is validated on the server: latitude −90…90, longitude −180…180, speed 0…300 km/h,
  and the time must be after the trip started and not in the future.
- A trip can't be ended with no GPS readings.
- Trip statistics are calculated **on the server** from the saved readings and can't be edited by hand.
- Riders get **404** for anyone else's trip; admins get **403** on Start Trip.

### Testing on a laptop

Laptops usually have no GPS, so choose **Demo (simulated GPS)**. It plays a sample ride near Cebu IT Park
that goes over 60 km/h. The readings go through exactly the same validation, saving, and alert logic as
real GPS, and the trip is labeled **Demo** in the history. To use real GPS, open the site on a phone.
Browsers only allow GPS on `https://` or `localhost`.

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
├── trips/                  # core feature: trip tracking & history
│   ├── models.py           # Trip, SpeedReading, SpeedAlert
│   ├── forms.py            # StartTripForm, ReadingForm (JSON validation), TripEditForm
│   ├── views.py            # start / track / readings API / end, list / detail / edit / delete
│   └── tests.py
├── templates/
│   ├── base.html, base_dashboard.html, 403.html, 404.html
│   ├── accounts/           # login, register, profile, change_password
│   ├── dashboards/         # user_dashboard, admin_dashboard, manage_users
│   ├── trips/              # start_trip, track_trip, trip_list, trip_detail, trip_edit, trip_confirm_delete
│   └── partials/           # icons, messages, form field, avatar, chart, ring
├── static/
│   ├── css/                # common.css, auth.css, dashboard.css, trips.css
│   ├── js/main.js          # toasts, mobile menu, photo preview
│   ├── js/trip-tracker.js  # GPS / demo ride, live speedometer, alerts, sends readings to Django
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
python manage.py migrate             # creates the account AND trip tables
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

---

## Git workflow

| Branch | Purpose |
|---|---|
| `main` | Stable releases only. Changes arrive only by Pull Request from `develop` |
| `develop` | Integration branch, created from `main` |
| `feature/trip-tracking` | Trip models, Start Trip, live GPS tracking, speed alerts, End Trip |
| `feature/trip-history` | Trip list, detail, edit, delete, dashboard integration, docs |

Flow: `feature/*` → Pull Request into `develop` → Pull Request from `develop` into `main`.
Merged feature branches are kept.
