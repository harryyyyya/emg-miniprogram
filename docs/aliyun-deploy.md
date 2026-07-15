# Aliyun Deployment Guide

This project deploys with:

- ECS: runs Docker, backend, and Caddy.
- RDS MySQL: stores users, forum posts/comments, devices, and EMG data.
- Caddy: provides HTTPS and reverse proxies to FastAPI.
- GitHub Actions: redeploys automatically after pushing to `main`.

## 1. Aliyun Console

Open these ECS security group ports:

- `22`: SSH login. Prefer allowing only your own IP.
- `80`: HTTP, required for certificate issuing and redirect.
- `443`: HTTPS, required by WeChat Mini Program production requests.

In RDS MySQL:

- Create database: `emg_hand`
- Character set: `utf8mb4`
- Create user: `emg_user`
- Give read/write permission to `emg_hand`
- Add ECS private IP to RDS whitelist, or bind the ECS security group.

## 2. Prepare ECS

Login:

```bash
ssh root@your-ecs-public-ip
```

Install Docker:

```bash
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker
```

Clone project:

```bash
mkdir -p /opt
cd /opt
git clone https://github.com/harryyyyya/emg-miniprogram.git weixin
cd /opt/weixin
```

Create root `.env`:

```bash
cp .env.deploy.example .env
nano .env
```

Set:

```env
API_DOMAIN=api.your-domain.com
```

Create backend `.env`:

```bash
cp backend/.env.production.example backend/.env
nano backend/.env
```

Set your real RDS address, database user, database password, and DeepSeek key.

## 3. Start Backend

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f backend
```

Test:

```bash
curl http://127.0.0.1:8000/ping
curl https://api.your-domain.com/ping
```

Expected:

```json
{"pong":true}
```

## 4. Configure GitHub Actions

In GitHub repository:

`Settings -> Secrets and variables -> Actions -> New repository secret`

Add:

- `ECS_HOST`: ECS public IP
- `ECS_USER`: usually `root`
- `ECS_SSH_PORT`: usually `22`
- `ECS_SSH_KEY`: private key content for SSH login

After this, every push to `main` deploys automatically.

## 5. Configure Mini Program

In `weixin/utils/request.js`, set:

```js
const PRODUCTION_BASE_URL = 'https://api.your-domain.com';
```

Then in WeChat Mini Program admin console:

- `request合法域名`: `https://api.your-domain.com`
- `uploadFile合法域名`: `https://api.your-domain.com`
- `downloadFile合法域名`: `https://api.your-domain.com`

Do not use LAN addresses like `http://192.168.x.x:8000` for production or real-device release testing.
