# DSA Practice Solver

A self-hosted backend for DSA / competitive-programming practice. It exposes
an OpenAI-compatible `/v1/chat/completions` endpoint that:

- Solves DSA/CP problems (text or screenshots) using **Gemini**.
- OCRs any attached screenshots with **Mistral OCR** and reconstructs a
  single problem statement before solving.
- Generates and manages its own client-facing API key, model alias
  (`dsa-solver`), and endpoint — you never invent these by hand.
- Keeps `MISTRAL_API_KEY` / `GEMINI_API_KEY` entirely server-side.

It's meant to be plugged into any client that supports the standard OpenAI
Chat Completions provider format (name, model, endpoint URL, API key).

## 1. Clone the project

```bash
git clone <your-fork-or-copy-of-this-repo>
cd dsa-practice-solver
```

## 2. Create `.env`

```bash
cp .env.example .env
```

## 3. Configure Mistral

Get an API key from the Mistral console and set:

```
MISTRAL_API_KEY=your-mistral-key
MISTRAL_OCR_MODEL=mistral-ocr-latest
```

## 4. Configure Gemini

Get an API key from Google AI Studio / Vertex and set:

```
GEMINI_API_KEY=your-gemini-key
GEMINI_MODEL=the-actual-gemini-model-name
```

`GEMINI_MODEL` is never exposed to clients — they only ever see the public
alias `dsa-solver`.

## 5. Set `APP_ADMIN_PASSWORD`

```
APP_ADMIN_PASSWORD=a-strong-password
ADMIN_SESSION_SECRET=a-long-random-string
```

`ADMIN_SESSION_SECRET` signs the admin session cookie — generate one with
`python3 -c "import secrets; print(secrets.token_urlsafe(32))"`.

## 6. Set `PUBLIC_BASE_URL`

```
PUBLIC_BASE_URL=https://your-actual-domain.com
```

If left blank, the server derives it from the incoming request, but setting
it explicitly is strongly recommended in production (reverse proxies,
custom domains, etc. can make request-derived URLs unreliable).

## 7. Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 8. Run with Docker

```bash
docker compose up --build
```

This builds the image, starts the container on port 8000, mounts a
persistent volume at `/app/data` (where the generated API key lives), and
runs a container health check against `/health`.

## 9. Deploy to a Docker-compatible host

Any host that can run a Dockerfile + persistent volume works (Render,
Fly.io, Railway, a VPS with Docker, etc.):

1. Set all variables from `.env.example` as environment variables/secrets
   on the host — **do not** bake `.env` into the image.
2. Mount a persistent volume/disk at `/app/data` so the generated API key
   survives restarts and redeploys.
3. Set `PUBLIC_BASE_URL` to the public URL the host gives you.
4. Deploy. The container's health check hits `GET /health`.

## 9b. Deploy to Vercel instead

Vercel doesn't run the Dockerfile — it uses its Python serverless
runtime, which this repo is also set up for via `api/index.py` and
`vercel.json`.

**Read this before choosing Vercel:** each request runs as a
short-lived serverless function with a hard timeout. `maxDuration` is
set to `60` seconds in `vercel.json`, but Vercel's **Hobby (free)
plan caps every function at 10 seconds regardless of that setting** —
only Pro and higher plans honor the full 60s. OCR + Gemini solve
requests, especially multi-image ones, can easily exceed 10 seconds.
If you're on the free plan, expect some requests to time out; a
persistent-process host (Render, Fly.io, Railway) doesn't have this
ceiling.

Steps:

1. Push this repo to GitHub/GitLab/Bitbucket (or use the Vercel CLI
   directly from this folder).
2. In the Vercel dashboard, **Import Project** and select this repo.
   Vercel should auto-detect the Python runtime from `vercel.json` —
   no framework preset needed.
3. Under **Environment Variables**, add everything from `.env.example`
   except `DATA_DIR` (leave it unset — the app detects Vercel
   automatically via the `VERCEL` env var it sets for you, and redirects
   storage to `/tmp` on its own).
4. Set `PUBLIC_BASE_URL` to the `.vercel.app` domain (or your custom
   domain) Vercel assigns you.
5. Deploy.
6. The client-facing API key still works exactly as described in
   **Persistence requirements** below — it's derived from
   `ADMIN_SESSION_SECRET`, needs no disk at all, and stays identical
   across every redeploy and every serverless cold start.

Or via the CLI, from inside `dsa-practice-solver/`:

```bash
npm i -g vercel
vercel          # follow prompts, set env vars when asked (or add them
                 # afterward in the dashboard)
vercel --prod
```

## 10. Open the admin page

Visit `https://your-domain.com/admin`, enter `APP_ADMIN_PASSWORD`, and
you'll see the provider name, model, endpoint, masked API key, status, and
request limit, plus buttons to show/regenerate the key and run a backend
test.

## 11. Retrieve the generated provider configuration

Via the UI (Show API Key), or via API once logged in (the login sets a
session cookie that subsequent requests reuse):

```bash
curl -c cookies.txt -X POST https://your-domain.com/admin/login \
  -H "Content-Type: application/json" \
  -d '{"password": "your-admin-password"}'

curl -b cookies.txt "https://your-domain.com/admin/provider?reveal=true"
```

## 12. Regenerate the provider API key

```bash
curl -b cookies.txt -X POST https://your-domain.com/admin/provider/regenerate
```

The previous key stops working immediately.

## 13. Configure the client

In your OpenAI-compatible client, add a provider:

```
Name:                DSA Practice Solver
Model:                dsa-solver
Endpoint URL:         https://your-domain.com/v1/chat/completions
API key:              GENERATED_BY_BACKEND
Status:               Active
```

> Note: this backend does not implement request rate limiting. If your
> client requires a rate-limit value to be entered, any number will work
> as a formality — it is not enforced server-side.

## 14. Test the endpoint with curl

Text-only:

```bash
curl https://your-domain.com/v1/chat/completions \
  -H "Authorization: Bearer YOUR_GENERATED_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dsa-solver",
    "messages": [
      {"role": "user", "content": "Solve this DSA problem in C++17: Given an array of n integers (n <= 1e5), find the maximum subarray sum."}
    ]
  }'
```

Multimodal (screenshot), with a tiny placeholder base64 PNG:

```bash
curl https://your-domain.com/v1/chat/completions \
  -H "Authorization: Bearer YOUR_GENERATED_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dsa-solver",
    "messages": [
      {
        "role": "user",
        "content": [
          {"type": "text", "text": "Solve this in C++17."},
          {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="}}
        ]
      }
    ]
  }'
```

## 15. Troubleshoot common failures

| Symptom | Likely cause |
|---|---|
| `401 invalid_api_key` on `/v1/chat/completions` | Wrong/old key — check `/admin/provider?reveal=true`, or the key was regenerated. |
| `502 upstream_error` | Mistral OCR or Gemini call failed — check `MISTRAL_API_KEY`/`GEMINI_API_KEY`/`GEMINI_MODEL` and provider status. Use "Test Backend" on `/admin`. |
| `413 request_too_large` | An image exceeds `MAX_IMAGE_SIZE_MB`. |
| Admin login fails | Confirm `APP_ADMIN_PASSWORD` matches what's set on the server; cookies must be enabled. |
| Provider key resets on every deploy | Make sure `/app/data` (or `DATA_DIR`) is a persistent volume, not ephemeral container storage. |

## Persistence requirements

**By default, no configuration is needed for the key to stay stable.**
The client-facing API key is deterministically derived from
`ADMIN_SESSION_SECRET` (a setting you already set once). Since that
value lives in an environment variable — not on disk — the exact same
key is reconstructed on every startup automatically, even on hosts that
wipe the filesystem on every deploy. The key is also cached to
`{DATA_DIR}/provider_key.json` so it doesn't need to be re-derived on
every request, but that file is disposable: if it's missing, the same
key is simply rebuilt from `ADMIN_SESSION_SECRET`.

**What this means in practice:**
- Set `ADMIN_SESSION_SECRET` once and don't change it → your client's
  API key never changes, across any number of restarts or redeploys,
  on any host, persistent disk or not.
- Changing `ADMIN_SESSION_SECRET` *will* change the derived key (they're
  cryptographically linked), so treat it as sensitive and stable, not
  something to rotate casually.

### Rotating the key on purpose

Clicking **Regenerate** on `/admin` mints a fresh random key immediately
and persists it to `DATA_DIR` — this works normally on any host with a
real persistent volume (Docker with the included `docker-compose.yml`
volume, or a paid Render disk). On a host with **no** persistent disk,
that rotated key only lives until the next redeploy wipes the
filesystem; after that, `get_or_create` falls back to reconstructing the
deterministic default again (derived from `ADMIN_SESSION_SECRET`) rather
than silently locking you out. If you need a rotation that survives
redeploys on such a host, set `PROVIDER_API_KEY` explicitly instead (see
below) — that always takes priority over the derived default.

### Explicit override: `PROVIDER_API_KEY`

If you want full manual control over the exact key value (e.g. to
choose a specific rotation, or to keep it decoupled from
`ADMIN_SESSION_SECRET`), set `PROVIDER_API_KEY` in your host's
environment variables:

```bash
python3 -c "import secrets; print('dsa_sk_' + secrets.token_urlsafe(32))"
```

When set, this value is used verbatim as the client-facing key and the
"Regenerate" button on `/admin` returns a 409 explaining that you need
to change the env var yourself and redeploy to rotate it — there's no
disk-free way to let the server pick a new random one and remember it
on its own in that mode.

For multi-instance deployments, replace `FileAPIKeyStore`
(`app/security/api_keys.py`) with a shared backend (database row, secrets
manager) — the class's interface (`get_or_create`, `regenerate`, `verify`)
is intentionally small to make this a drop-in swap.

## Rate limiting

This backend does **not** implement request rate limiting — every
authenticated request is processed regardless of volume. If you need to
cap usage (e.g. to control Gemini/Mistral spend), put a rate limiter in
front of this service (reverse proxy, API gateway, or your client
platform's own limiting) rather than in the backend itself.

## Security notes

- `MISTRAL_API_KEY` and `GEMINI_API_KEY` are never accepted as client
  credentials and never appear in any response body.
- The admin password is never embedded in frontend JavaScript; the admin
  page authenticates via a signed, HTTP-only session cookie.
- Authorization headers, API keys, and base64 image data are never logged
  — only request IDs, image counts, durations, and status codes are.
- Screenshots are processed in memory and are not written to disk.
- This project intentionally does **not** implement, and will not add,
  screen monitoring, stealth/covert capture, or anything designed to
  conceal AI assistance during interviews, proctored exams, or rated
  contests. It's a study tool: you paste in a problem, it helps you solve
  it, out in the open.

## Verification performed before delivery

- ✅ All Python files compiled successfully (`py_compile`), no syntax
  errors.
- ✅ Full test suite written (`tests/`) covering health, auth, admin,
  provider config/key rotation, and chat completions (text-only and
  multimodal, image validation), with Mistral/Gemini mocked throughout.
- ⚠️ **Not verified in this environment**: actually running
  `pip install -r requirements.txt`, `pytest`, `uvicorn`, or `docker build`
  — the sandbox this project was built in has no outbound network access,
  so dependencies could not be installed here. Please run:

  ```bash
  pip install -r requirements.txt
  pytest
  uvicorn app.main:app --reload
  docker compose up --build
  ```

  and report back if anything fails — the code has been written and
  reviewed carefully, but this step substitutes for the "install, test,
  build, verify" pass that couldn't be executed automatically here.
