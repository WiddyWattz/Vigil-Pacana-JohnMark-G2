# Vigil — Account Feature (IM2)

Django web application for Vigil's Account Feature (registration, login/logout,
role-based dashboards, user profiles), using PostgreSQL on Supabase.

Author: John Mark P. Pacaña — Section G2

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in SECRET_KEY and DATABASE_URL
python manage.py migrate
python manage.py runserver
```
