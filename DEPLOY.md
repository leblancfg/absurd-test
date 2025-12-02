# Deployment Guide

This document outlines the steps taken to deploy the absurd-test application to a production server.

## Prerequisites

- Ubuntu server with SSH access
- Domain name with DNS configured to point to server IP
- User account with sudo privileges

## Initial Server Setup

### 1. Install System Dependencies

```bash
# Update package list
sudo apt update

# Install essential packages
sudo apt install -y git postgresql postgresql-contrib python3-pip python3-venv curl

# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

### 2. Configure PostgreSQL

PostgreSQL needs to be configured to accept password authentication:

```bash
# Edit pg_hba.conf to use md5 authentication
sudo sed -i 's/^local.*all.*all.*peer$/local   all             all                                     md5/' /etc/postgresql/17/main/pg_hba.conf

# Restart PostgreSQL
sudo systemctl restart postgresql
```

### 3. Create Database and User

```bash
# Create PostgreSQL user
sudo -u postgres psql -c "CREATE USER absurd_user WITH PASSWORD 'your-secure-password';"

# Create database
sudo -u postgres psql -c "CREATE DATABASE absurd_test OWNER absurd_user;"

# Grant privileges
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE absurd_test TO absurd_user;"
```

## Application Setup

### 1. Clone Repository

```bash
cd ~
git clone https://github.com/leblancfg/absurd-test.git
cd absurd-test
```

### 2. Configure Environment

Create a `.env` file with your configuration:

```bash
cat > .env << EOF
DATABASE_URL=postgresql://absurd_user:your-secure-password@localhost/absurd_test
OPENAI_API_KEY=your-key-here
KIOSK=true
EOF
```

**Important Environment Variables:**
- `DATABASE_URL`: PostgreSQL connection string
- `OPENAI_API_KEY`: OpenAI API key (not used in KIOSK mode)
- `KIOSK`: Set to `true` to use Oblique Strategies instead of AI API calls

### 3. Install Python Dependencies

```bash
~/.local/bin/uv sync
```

### 4. Bootstrap Database

```bash
# Apply Absurd schema
PGPASSWORD=your-secure-password psql -h localhost -U absurd_user -d absurd_test -f src/absurd_test/sql/absurd.sql

# Create Absurd queue
PGPASSWORD=your-secure-password psql -h localhost -U absurd_user -d absurd_test -c "SELECT absurd.create_queue('agent_tasks');"

# Run Alembic migrations
~/.local/bin/uv run alembic upgrade head
```

## Systemd Services

### 1. Create API Service

Create `/etc/systemd/system/absurd-api.service`:

```ini
[Unit]
Description=Absurd Test API
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=your-username
WorkingDirectory=/home/your-username/absurd-test
Environment="PATH=/home/your-username/.local/bin:/usr/local/bin:/usr/bin:/bin"
Environment="DATABASE_URL=postgresql://absurd_user:your-secure-password@localhost/absurd_test"
ExecStart=/home/your-username/.local/bin/uv run uvicorn absurd_test.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 2. Create Worker Service

Create `/etc/systemd/system/absurd-worker.service`:

```ini
[Unit]
Description=Absurd Test Worker
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=your-username
WorkingDirectory=/home/your-username/absurd-test
Environment="PATH=/home/your-username/.local/bin:/usr/local/bin:/usr/bin:/bin"
Environment="DATABASE_URL=postgresql://absurd_user:your-secure-password@localhost/absurd_test"
ExecStart=/home/your-username/.local/bin/uv run python -m absurd_test.worker
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 3. Enable and Start Services

```bash
sudo systemctl daemon-reload
sudo systemctl enable absurd-api absurd-worker
sudo systemctl start absurd-api absurd-worker

# Check status
sudo systemctl status absurd-api absurd-worker
```

## Reverse Proxy Setup

### Configure Nginx

If Nginx is already installed and managing other sites, add a new site configuration:

Create `/etc/nginx/sites-available/absurd`:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name your-subdomain.yourdomain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/absurd /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### SSL Certificate with Certbot

```bash
sudo certbot --nginx -d your-subdomain.yourdomain.com --non-interactive --agree-tos --email your-email@example.com
```

Certbot will automatically:
- Obtain an SSL certificate
- Configure Nginx to use HTTPS
- Set up automatic renewal

## Deploying Updates

When you have new code changes:

```bash
# SSH into the server
ssh user@your-server-ip

# Navigate to project directory
cd absurd-test

# Pull latest changes
git pull

# Restart services
sudo systemctl restart absurd-api absurd-worker
```

**Note:** If dependencies changed, run `~/.local/bin/uv sync` before restarting.

## Monitoring

### Check Service Logs

```bash
# API logs
sudo journalctl -u absurd-api -f

# Worker logs
sudo journalctl -u absurd-worker -f

# PostgreSQL logs
sudo journalctl -u postgresql -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Check Service Status

```bash
sudo systemctl status absurd-api
sudo systemctl status absurd-worker
sudo systemctl status postgresql
sudo systemctl status nginx
```

## Firewall Configuration

**⚠️ IMPORTANT:** Be extremely careful with firewall rules to avoid locking yourself out!

Only modify firewall rules if you know what you're doing. The basic ports needed are:
- `22` (SSH) - **Must remain open**
- `80` (HTTP) - For initial Certbot verification
- `443` (HTTPS) - For secure web traffic

## Troubleshooting

### Services Won't Start

Check the logs:
```bash
sudo journalctl -u absurd-api -n 50
sudo journalctl -u absurd-worker -n 50
```

Common issues:
- Missing environment variables in `.env`
- Database connection errors (check `DATABASE_URL`)
- Port 8000 already in use

### Database Connection Issues

Verify PostgreSQL is running and accepting connections:
```bash
systemctl status postgresql
PGPASSWORD=your-password psql -h localhost -U absurd_user -d absurd_test -c "SELECT 1;"
```

### Worker Not Processing Tasks

Check that KIOSK mode is enabled:
```bash
sudo journalctl -u absurd-worker | grep "Starting Absurd worker"
```

Should show: `KIOSK MODE (Oblique Strategies)`

## KIOSK Mode

The application runs in KIOSK mode when `KIOSK=true` is set in the environment. In this mode:

- No OpenAI API calls are made
- Random Oblique Strategies are returned instead
- ~3 second delay with jitter is applied
- Footer displays "Hosted on colocataires.dev" link
- About page shows KIOSK mode explanation

This mode is ideal for public demos where you want to showcase the infrastructure without exposing API credentials.

## Security Notes

- Never commit `.env` files with real credentials to git
- Use strong passwords for database users
- Keep the system updated: `sudo apt update && sudo apt upgrade`
- Review Nginx logs regularly for suspicious activity
- Consider setting up fail2ban for SSH brute-force protection
- Restrict database access to localhost only
