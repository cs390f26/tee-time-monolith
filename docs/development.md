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

Install MySQL and start it (Homebrew on macOS):

```bash
brew install mysql
brew services start mysql
```

Create the application database, a separate database for pytest, and a user. The app connects to `127.0.0.1` over TCP, so that account is separate from `localhost`:

```bash
mysql -u root <<'EOF'
CREATE DATABASE IF NOT EXISTS tee_time;
CREATE DATABASE IF NOT EXISTS tee_time_test;
CREATE USER IF NOT EXISTS 'tee_time'@'localhost' IDENTIFIED BY 'tee_time';
CREATE USER IF NOT EXISTS 'tee_time'@'127.0.0.1' IDENTIFIED BY 'tee_time';
GRANT ALL PRIVILEGES ON tee_time.* TO 'tee_time'@'localhost';
GRANT ALL PRIVILEGES ON tee_time.* TO 'tee_time'@'127.0.0.1';
GRANT ALL PRIVILEGES ON tee_time_test.* TO 'tee_time'@'localhost';
GRANT ALL PRIVILEGES ON tee_time_test.* TO 'tee_time'@'127.0.0.1';
FLUSH PRIVILEGES;
EOF
```

Create a gitignored `.env` in the repo root:

```
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=tee_time
MYSQL_PASSWORD=tee_time
MYSQL_DATABASE=tee_time
```

`ensure_settings()` in `src/tee_time/settings.py` loads that file and exits if `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, or `MYSQL_DATABASE` is missing. `MYSQL_PORT` defaults to 3306.

On startup, `launch()` in `src/tee_time/app.py` calls `ClubStorage.create_schema()`, which applies only the `CREATE TABLE` statements from `scripts/schema.sql` as `CREATE TABLE IF NOT EXISTS`. It does not run the `DROP TABLE` lines, so starting the app does not wipe an existing database. To rebuild an empty database (this drops the tables):

```bash
mysql -u tee_time -ptee_time tee_time < scripts/schema.sql
```

## Seed

After the tables exist, load `scripts/seed-data.sql` (twelve members, slots for Oct 7–13 2026, and bookings):

```bash
mysql -u tee_time -ptee_time tee_time < scripts/seed-data.sql
```

Running the inserts twice fails on primary keys. Reset by applying `schema.sql` (drops tables) and then `seed-data.sql` again:

```bash
mysql -u tee_time -ptee_time tee_time < scripts/schema.sql
mysql -u tee_time -ptee_time tee_time < scripts/seed-data.sql
```

The running app reads MySQL. `data/sample-data.json` is the same roster in JSON and is not loaded at startup. Unit tests use the `tee_time_test` database and leave `tee_time` alone.

## Run

```bash
python -m tee_time.app
```

Serves http://127.0.0.1:5000/ with Flask debug on. A missing setting or unreachable database prints the error and exits with status 1.
