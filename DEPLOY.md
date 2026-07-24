# Deploying to Dokku (Python buildpack)

Deploy with **`git push dokku`** and the [Heroku Python buildpack](https://github.com/heroku/heroku-buildpack-python).
No Docker image build is required on your machine.

The repo includes the files that buildpack expects:

| File | Purpose |
|------|---------|
| `Procfile` | Starts Gunicorn on Dokku's `$PORT` |
| `requirements.txt` | Production dependencies (regenerate with command below) |
| `runtime.txt` | Pins Python 3.13.2 |

No `.env` file is deployed — set secrets with `dokku config:set`. Preset flows
under `data/flows/` ship with the app; user saves are ephemeral on redeploy.

## Prerequisites

- Dokku app with git remote access (`git push dokku`)
- APS app at https://aps.autodesk.com/myapps
- HTTPS on your Dokku app URL (Let's Encrypt plugin recommended)

## One-time Dokku setup

On the Dokku server:

```bash
dokku apps:create dx-flow
dokku builder:set dx-flow selected herokuish
dokku buildpacks:clear dx-flow
dokku buildpacks:add dx-flow heroku/python
dokku domains:set dx-flow your-domain.example
dokku letsencrypt:enable dx-flow   # if using the Let's Encrypt plugin
```

Register this callback URL in your APS app:

```
https://your-domain.example/oauth/callback
```

Set config vars:

```bash
dokku config:set dx-flow \
  APS_CLIENT_ID=your_client_id \
  APS_CLIENT_SECRET=your_client_secret \
  APS_REDIRECT_URI=https://your-domain.example/oauth/callback \
  APS_SCOPE="user-profile:read data:read viewables:read" \
  FLASK_SECRET_KEY="$(openssl rand -hex 32)" \
  FLASK_DEBUG=0 \
  BEHIND_PROXY=1
```

`BEHIND_PROXY=1` enables `ProxyFix` so OAuth redirect URLs use `https://` behind
nginx. With `FLASK_DEBUG=0`, secure session cookies are enabled automatically.

## Deploy

From your machine:

```bash
git remote add dokku dokku@your-dokku-host:dx-flow   # once
git push dokku main
```

Dokku installs dependencies from `requirements.txt`, uses Python from
`runtime.txt`, and runs the `web` process from `Procfile`.

## Regenerating `requirements.txt`

When you change dependencies in `pyproject.toml`, refresh the lockfile and export:

```bash
uv sync
uv export --no-dev --no-emit-project -o requirements.txt
git add requirements.txt uv.lock
```

Commit `Procfile` and `runtime.txt` only when those change.

## Local production smoke test

Run the same stack Dokku uses:

```bash
uv sync
export FLASK_DEBUG=0 BEHIND_PROXY=0
export APS_CLIENT_ID=... APS_CLIENT_SECRET=... APS_REDIRECT_URI=http://localhost:8080/oauth/callback
export FLASK_SECRET_KEY=local-test-secret PORT=8080
gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 run:app
```

## What persists on Dokku

| Data | Behavior |
|------|----------|
| Preset flows in `data/flows/` | Shipped in the slug — survive redeploy |
| User-saved flows (Save button) | Container disk — lost on redeploy/restart |
| CSV/Excel Output | Browser download only — nothing on server |
| OAuth session | Cookie — lost when token expires or user logs off |

## Troubleshooting

- **Build fails on Python version** — check `runtime.txt` matches a version the
  buildpack supports (3.13.x for this app).
- **OAuth redirect mismatch** — `APS_REDIRECT_URI` must exactly match the APS
  app callback URL (scheme + host + path).
- **Login fails on Dokku but works locally** — confirm `BEHIND_PROXY=1`,
  HTTPS, and `FLASK_DEBUG=0`.
- **Module not found after adding a dependency** — regenerate and commit
  `requirements.txt`.

## Alternative: Docker / registry sync

If your Dokku host only supports pulling a pre-built image (e.g. Autodesk
`sync-from-docker`), use a `Dockerfile` instead of this buildpack flow. The
buildpack path above is the standard `git push dokku` approach.
