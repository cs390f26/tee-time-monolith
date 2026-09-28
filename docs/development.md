# Development

Local setup for the tee-time Flask app. Commands assume the repo root and Python 3.12+.

## Virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

`.venv` is gitignored.

## Install

With the virtual environment active:

```bash
pip install -r requirements.txt
pip install -e .
```

The editable install (`package_dir={"": "src"}` in `setup.py`) is what makes `import tee_time` and `python -m tee_time.app` work.

## Database

Create a gitignored `.env` in the repo root:

```
DATABASE_PATH=club.sqlite
```

`ensure_settings()` in `src/tee_time/settings.py` loads that file and exits if `DATABASE_PATH` is missing. A relative path is resolved from the working directory, so start the app from the repo root. `*.sqlite` is gitignored.

On startup, `launch()` in `src/tee_time/app.py` calls `ClubStorage.create_schema()`, which applies only the `CREATE TABLE` statements from `scripts/schema.sql` as `CREATE TABLE IF NOT EXISTS`. It does not run the `DROP TABLE` lines, so starting the app does not wipe an existing file. To rebuild an empty database (this drops the tables):

```bash
sqlite3 club.sqlite < scripts/schema.sql
```

## Seed

After the tables exist, load `scripts/seed-data.sql` (twelve members, slots for Sep 14–20 2026, and bookings):

```bash
sqlite3 club.sqlite < scripts/seed-data.sql
```

Running the inserts twice fails on primary keys. Reset by applying `schema.sql` (drops tables) and then `seed-data.sql` again:

```bash
sqlite3 club.sqlite < scripts/schema.sql
sqlite3 club.sqlite < scripts/seed-data.sql
```

The running app reads SQLite. `data/sample-data.json` is the same roster in JSON and is not loaded at startup.

## Run

```bash
python -m tee_time.app
```

Serves http://127.0.0.1:5000/ with Flask debug on. A missing setting or unreachable database prints the error and exits with status 1.
