# tezsandesh.digital — Production Deployment Guide (Hostinger VPS)

Stack: Ubuntu 22.04/24.04 · Nginx · MongoDB 7 · FastAPI (Gunicorn + Uvicorn workers) · React build (static)

Architecture on the VPS:

```
Internet → Nginx (443, SSL)
             ├── /            → React static build  (/var/www/tezsandesh)
             └── /api/*       → Gunicorn/Uvicorn on 127.0.0.1:8001
MongoDB → 127.0.0.1:27017 (localhost only)
```

Replace `yourdomain.com` with your real domain everywhere below.

---

## 1. Server prerequisites

```bash
ssh root@YOUR_VPS_IP

apt update && apt upgrade -y
apt install -y nginx git curl python3 python3-venv python3-pip build-essential \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libffi-dev shared-mime-info
# (pango/gdk-pixbuf are required by WeasyPrint for PDF generation)

# Node.js 20 + yarn
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs
npm install -g yarn

# MongoDB 7
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | gpg --dearmor -o /usr/share/keyrings/mongodb-server-7.0.gpg
echo "deb [signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" > /etc/apt/sources.list.d/mongodb-org-7.0.list
apt update && apt install -y mongodb-org
systemctl enable --now mongod
```

DNS: point an **A record** for `yourdomain.com` (and `www`) to your VPS IP before requesting SSL.

## 2. Get the code

Push this repo to GitHub first (use the **"Save to GitHub"** button in the Emergent chat input), then:

```bash
mkdir -p /opt && cd /opt
git clone https://github.com/YOUR_USER/YOUR_REPO.git tezsandesh
cd tezsandesh
```

## 3. Backend setup

```bash
cd /opt/tezsandesh/backend
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# Production environment file
cp .env.production.example .env
nano .env
```

Fill in `.env` (see `.env.production.example`). Critical values:

| Key | Value |
|---|---|
| `DB_NAME` | `tezsandesh_production` |
| `CORS_ORIGINS` | `https://yourdomain.com,https://www.yourdomain.com` |
| `JWT_SECRET` | output of `openssl rand -hex 32` |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | your real super-admin login (auto-seeded at first start) |
| `DEMO_MODE` | **`false`** — disables demo sample data AND disables mock WhatsApp sends (missing creds become hard errors) |
| `WHATSAPP_ACCESS_TOKEN` | permanent System User token |
| `WHATSAPP_PHONE_NUMBER_ID` | from Meta → WhatsApp → API Setup |
| `WHATSAPP_VERIFY_TOKEN` | any random string, same one you paste in Meta dashboard |
| `WHATSAPP_APP_SECRET` | Meta App → Settings → Basic → App Secret (**enables webhook signature verification**) |

Quick boot test with Gunicorn:

```bash
cd /opt/tezsandesh/backend
./venv/bin/gunicorn server:app -k uvicorn.workers.UvicornWorker -b 127.0.0.1:8001 --workers 2
# Ctrl+C after you see "Application startup complete."
```

### systemd service

```bash
cat > /etc/systemd/system/tezsandesh-backend.service << 'EOF'
[Unit]
Description=tezsandesh.digital FastAPI backend
After=network.target mongod.service

[Service]
WorkingDirectory=/opt/tezsandesh/backend
ExecStart=/opt/tezsandesh/backend/venv/bin/gunicorn server:app -k uvicorn.workers.UvicornWorker -b 127.0.0.1:8001 --workers 2 --timeout 120
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now tezsandesh-backend
systemctl status tezsandesh-backend --no-pager
```

> Note: keep `--workers 2` (not more). The app runs in-process background schedulers
> (campaign scheduler + reminder loop); more workers duplicate the schedulers.

## 4. Frontend build

```bash
cd /opt/tezsandesh/frontend
cp .env.production.example .env      # REACT_APP_BACKEND_URL stays EMPTY → same-origin /api
yarn install                          # (or: npm install)
yarn build                            # (or: npm run build)

mkdir -p /var/www/tezsandesh
cp -r build/* /var/www/tezsandesh/
```

`REACT_APP_BACKEND_URL` **must be empty** in production — the frontend then calls
`/api/...` on the same domain, which Nginx proxies to the backend. No preview or
Emergent URLs remain anywhere in the build.

## 5. Nginx + SSL

```bash
cat > /etc/nginx/sites-available/tezsandesh << 'EOF'
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    root /var/www/tezsandesh;
    index index.html;
    client_max_body_size 25M;

    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    location / {
        try_files $uri /index.html;
    }
}
EOF

ln -sf /etc/nginx/sites-available/tezsandesh /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

# SSL (Let's Encrypt) — DNS must already point to this VPS
apt install -y certbot python3-certbot-nginx
certbot --nginx -d yourdomain.com -d www.yourdomain.com --redirect
```

Certbot auto-renews via systemd timer (`certbot renew --dry-run` to verify).

## 6. Verify production readiness

```bash
# Backend health
curl -s https://yourdomain.com/api/ | head -1
# → {"name":"tezsandesh.digital API", ...}

# WhatsApp webhook verification (use YOUR verify token)
curl -s "https://yourdomain.com/api/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=YOUR_VERIFY_TOKEN&hub.challenge=test123"
# → test123

# Login
curl -s -X POST https://yourdomain.com/api/auth/login -H "Content-Type: application/json" \
  -d '{"email":"admin@yourdomain.com","password":"YOUR_PASSWORD"}'
```

## 7. Meta dashboard (final step)

1. developers.facebook.com → your App → **WhatsApp → Configuration**
2. Callback URL: `https://yourdomain.com/api/webhook/whatsapp`
3. Verify Token: the `WHATSAPP_VERIFY_TOKEN` from your `.env`
4. **Verify and Save** → subscribe to the **`messages`** webhook field
5. Send a test: log in → Providers page → Meta card → Quick Test Send

## 8. Updating the app later

```bash
cd /opt/tezsandesh
git pull
cd backend  && ./venv/bin/pip install -r requirements.txt
cd ../frontend && yarn install && yarn build && cp -r build/* /var/www/tezsandesh/
systemctl restart tezsandesh-backend
systemctl restart nginx
```

## 9. Database

- **No migrations needed** — MongoDB collections and indexes are created automatically
  on first backend startup (`on_startup` → `create_index` calls + admin user seeding
  from `ADMIN_EMAIL`/`ADMIN_PASSWORD`).
- With `DEMO_MODE=false` no demo contacts/campaigns are seeded — you start clean.
- Backups (daily cron suggestion):

```bash
cat > /etc/cron.daily/mongo-backup << 'EOF'
#!/bin/bash
mongodump --db tezsandesh_production --out /var/backups/mongo/$(date +%F)
find /var/backups/mongo -maxdepth 1 -mtime +14 -exec rm -rf {} \;
EOF
chmod +x /etc/cron.daily/mongo-backup
```

## 10. Security checklist

- [ ] `JWT_SECRET` rotated (`openssl rand -hex 32`)
- [ ] `ADMIN_PASSWORD` strong + changed after first login (Settings → change password)
- [ ] `DEMO_MODE=false`
- [ ] `WHATSAPP_APP_SECRET` set → webhook signature verification active
- [ ] `CORS_ORIGINS` restricted to your domain (no `*`)
- [ ] MongoDB bound to localhost only (default) — `grep bindIp /etc/mongod.conf`
- [ ] Firewall: `ufw allow OpenSSH && ufw allow 'Nginx Full' && ufw enable`
- [ ] SSL active + HTTP→HTTPS redirect (certbot `--redirect`)
- [ ] Permanent System User token in use (not the temporary 24h token)
