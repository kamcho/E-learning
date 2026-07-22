# Deploying Elearning to a DigitalOcean Droplet

Stack: **Ubuntu 24.04 + Nginx + Gunicorn (uvicorn ASGI workers) + PostgreSQL**

> Why this stack? See "Best approach" at the bottom. In short: `gunicorn` gives
> rock-solid process management, `uvicorn` workers make it fully **async/ASGI**,
> and `nginx` handles TLS + static files.

Throughout this guide:
- App directory: `/srv/elearning`
- App user: `elearning`
- Unix socket: `/run/elearning/elearning.sock`
- Droplet IP: **159.223.143.29**
- Domain: **somasmartassesments.com** (www + apex)

---

## 0. Local sanity check (on your Windows machine, before deploying)

Local dev keeps using **SQLite** automatically (no `DB_ENGINE` set in your `.env`).

```powershell
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

---

## 1. Create the droplet & log in

Create an Ubuntu 24.04 droplet in the DigitalOcean panel, then from your machine:

```bash
ssh root@159.223.143.29
```

## 2. System packages

```bash
apt update && apt upgrade -y
apt install -y python3 python3-venv python3-dev build-essential \
    libpq-dev postgresql postgresql-contrib nginx git curl ufw
```

## 3. Firewall

```bash
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
```

## 4. Create the app user

```bash
adduser --system --group --home /srv/elearning elearning
usermod -aG www-data elearning
```

## 5. Get the code onto the droplet

**Option A — git (recommended):**

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git /srv/elearning
```

**Option B — copy from your PC** (run this on your Windows machine, not the droplet):

```powershell
scp -r C:\Users\USER\Downloads\edu\Elearning\* root@159.223.143.29:/srv/elearning/
```

Then fix ownership on the droplet:

```bash
chown -R elearning:www-data /srv/elearning
```

## 6. PostgreSQL: create the database & user

```bash
sudo -u postgres psql <<'SQL'
CREATE DATABASE elearning;
CREATE USER elearning WITH PASSWORD '141778215aA!';
ALTER ROLE elearning SET client_encoding TO 'utf8';
ALTER ROLE elearning SET default_transaction_isolation TO 'read committed';
ALTER ROLE elearning SET timezone TO 'Africa/Nairobi';
GRANT ALL PRIVILEGES ON DATABASE elearning TO elearning;
\c elearning
GRANT ALL ON SCHEMA public TO elearning;
SQL
```

## 7. Python virtualenv & dependencies

```bash
cd /srv/elearning
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

## 8. Create the production `.env`

```bash
cd /srv/elearning
cp .env.production.example .env
nano .env
```

Fill it in. The important bits for this droplet:

```
SECRET_KEY=<paste output of the command below>
DEBUG=False
ALLOWED_HOSTS=somasmartassesments.com,www.somasmartassesments.com,159.223.143.29
CSRF_TRUSTED_ORIGINS=http://somasmartassesments.com,http://www.somasmartassesments.com,https://somasmartassesments.com,https://www.somasmartassesments.com,http://159.223.143.29
DB_ENGINE=postgres
DB_NAME=elearning
DB_USER=elearning
DB_PASSWORD=<same password you set for the Postgres elearning user>
DB_HOST=127.0.0.1
DB_PORT=5432
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
```

> Keep cookie secure flags **False** until Certbot HTTPS is working. Then set them to True and enable `SECURE_SSL_REDIRECT`.

Generate a strong secret key:

```bash
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Lock down the file (it holds secrets):

```bash
chown elearning:www-data /srv/elearning/.env
chmod 640 /srv/elearning/.env
```

## 9. Migrate, collect static, create admin

```bash
cd /srv/elearning
sudo -u elearning .venv/bin/python manage.py migrate
sudo -u elearning .venv/bin/python manage.py collectstatic --noinput
sudo -u elearning .venv/bin/python manage.py createsuperuser
```

## 10. Gunicorn systemd service (gunicorn + uvicorn workers)

```bash
cp /srv/elearning/deploy/elearning.service /etc/systemd/system/elearning.service
systemctl daemon-reload
systemctl enable --now elearning
systemctl status elearning --no-pager
```

Check for errors any time with:

```bash
journalctl -u elearning -e --no-pager
```

## 11. Nginx

```bash
cp /srv/elearning/deploy/nginx.conf /etc/nginx/sites-available/elearning
ln -sf /etc/nginx/sites-available/elearning /etc/nginx/sites-enabled/elearning
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx
```

Visit **http://somasmartassesments.com** (or **http://159.223.143.29**) — the site should load.

## 12. HTTPS with Let's Encrypt

DNS A records for `@` and `www` must already point to `159.223.143.29`.

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d somasmartassesments.com -d www.somasmartassesments.com
```

Then turn on strict HTTPS in `/srv/elearning/.env`:

```
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
CSRF_TRUSTED_ORIGINS=https://somasmartassesments.com,https://www.somasmartassesments.com
MPESA_CALLBACK_BASE_URL=https://somasmartassesments.com
```

Restart the app:

```bash
systemctl restart elearning
```

---

## Updating the app later (redeploy)

### Automatic (GitHub Actions)

On every push to `main`, GitHub Actions SSHs into the droplet and runs
`deploy/update.sh` (git pull → pip install → migrate → collectstatic →
restart `elearning` → reload nginx).

**One-time setup**

1. On the droplet, the app directory must be a **git clone** of this repo
   (not only an `scp` copy):

   ```bash
   # If you previously copied files with scp, convert to git:
   cd /srv
   mv elearning elearning.bak
   git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git elearning
   # restore production secrets + venv if needed:
   cp elearning.bak/.env elearning/.env
   # either move the old venv or recreate it:
   #   mv elearning.bak/.venv elearning/.venv
   #   OR: cd elearning && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   chown -R elearning:www-data /srv/elearning
   chmod 640 /srv/elearning/.env
   chmod +x /srv/elearning/deploy/update.sh
   ```

2. In the GitHub repo → **Settings → Secrets and variables → Actions**,
   add these repository secrets:

   | Secret | Value |
   |---|---|
   | `DROPLET_HOST` | `159.223.143.29` |
   | `DROPLET_USER` | `root` |
   | `DROPLET_SSH_PASSWORD` | your droplet root password |
   | `DROPLET_PORT` | `22` (optional) |

   > Prefer an SSH key long-term (more secure than password). For now password
   > auth works with `appleboy/ssh-action` via `DROPLET_SSH_PASSWORD`.

3. Push to `main` (or run the workflow manually under **Actions → Deploy to droplet**).

The workflow file lives at `.github/workflows/deploy.yml`.

### Manual (on the droplet)

```bash
cd /srv/elearning
bash deploy/update.sh
```

Or step-by-step:

```bash
cd /srv/elearning
sudo -u elearning git pull
sudo -u elearning .venv/bin/pip install -r requirements.txt
sudo -u elearning .venv/bin/python manage.py migrate
sudo -u elearning .venv/bin/python manage.py collectstatic --noinput
systemctl restart elearning
```

---

## Troubleshooting

| Symptom | Command / Fix |
|---|---|
| App won't start | `journalctl -u elearning -e --no-pager` |
| 502 Bad Gateway | Check the service is running and the socket exists: `systemctl status elearning`, `ls -l /run/elearning/` |
| Static files missing | Re-run `collectstatic`; confirm nginx `alias` path = `/srv/elearning/staticfiles/` |
| CSRF errors on login | Add your https origin to `CSRF_TRUSTED_ORIGINS` in `.env`, restart |
| DB auth fails | Confirm `DB_PASSWORD` in `.env` matches the Postgres role password |
| nginx config error | `nginx -t` |

---

## Best approach (why gunicorn + uvicorn, not daphne)

You asked for an async server "because of AI". Here's the reasoning for this
project specifically:

- Your AI code (`core/ai/client.py`) calls OpenAI **synchronously** and there
  are **no WebSockets / Django Channels** anywhere in the project.
- **Daphne** is the right choice mainly when you use **Django Channels /
  WebSockets** (live chat, real-time streaming over a socket). You don't, so
  Daphne would add complexity with no benefit.
- **Gunicorn + Uvicorn workers** is the recommended production setup for an
  async Django (ASGI) app: Gunicorn provides mature process management (worker
  restarts, timeouts, graceful reloads, `systemd` integration) while the
  Uvicorn workers give you a real ASGI/async event loop. You get async
  request handling now, and you're ready if you later add streaming AI
  responses or WebSockets — you'd just add Channels and, if needed, switch
  those routes to Daphne, keeping everything else on Gunicorn.

That's exactly what `deploy/gunicorn.conf.py` + `deploy/elearning.service`
configure: `gunicorn -k uvicorn_worker.UvicornWorker Elearning.asgi:application`.
