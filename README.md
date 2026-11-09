# Microservices: Auth, Posts and Search

Three Python (FastAPI) services behind an nginx gateway, run together with Docker Compose.

```
                     ┌──────────────┐
  client ──:8080──▶  │ gateway      │  nginx
                     └──┬────┬────┬─┘
            /auth/*     │    │    │  /search
         ┌──────────────┘    │    └───────────────┐
         ▼                   ▼ /posts             ▼
   ┌───────────┐      ┌───────────┐  events  ┌───────────┐
   │ auth      │      │ posts     │ ───────▶ │ search    │
   │ JWT issue │      │ CRUD      │  Redis   │ BM25      │
   └─────┬─────┘      └─────┬─────┘  stream  │ index     │
         ▼                  ▼                └───────────┘
     auth-db            posts-db
    (Postgres)         (Postgres)
```

| Service  | What it does | Storage |
|----------|--------------|---------|
| `auth`   | Register / log in users, issue JWTs (HS256) | its own Postgres |
| `posts`  | Create, read, update, delete posts; checks JWTs locally with the shared secret; sends every change to the `posts.events` Redis stream | its own Postgres |
| `search` | Your search engine: an in-memory **BM25 inverted index** ([index.py](services/search/app/index.py)) kept up to date from the Redis stream. On startup it replays the stream from the start, so the index rebuilds itself. | in memory (rebuilt from the stream) |
| `gateway`| The only public port; routes `/auth/`, `/posts`, `/search` | – |

Each service has its own database ("database per service"). Services never read each other's data directly: auth shares a JWT secret with posts, and posts sends events to search.

## Run it

1. Start Docker Desktop.
2. Create `.env` (one with a random `JWT_SECRET` is already generated; it is ignored by git):
   ```bash
   cp .env.example .env
   ```
3. Build and start:
   ```bash
   docker compose up --build -d
   ```
4. Check status: `docker compose ps`. Logs: `docker compose logs -f search`.

## Try it

```bash
# register + log in
curl -X POST localhost:8080/auth/register -H "Content-Type: application/json" -d '{"username":"natasha","password":"supersecret"}'
TOKEN=$(curl -s -X POST localhost:8080/auth/login -H "Content-Type: application/json" -d '{"username":"natasha","password":"supersecret"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# create posts
curl -X POST localhost:8080/posts -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"title":"Intro to transformers","body":"Attention is the key idea behind transformer models."}'
curl -X POST localhost:8080/posts -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"title":"Docker basics","body":"Containers package an app with its dependencies."}'

# search
curl "localhost:8080/search?q=transformer+attention"
```

## API

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/register` | – | `{username, password}` → user |
| POST | `/auth/login` | – | `{username, password}` → `{access_token}` |
| GET | `/auth/me` | Bearer | Current user from token |
| GET | `/posts?limit=&offset=&author=` | – | List posts |
| GET | `/posts/{id}` | – | Get a post |
| POST | `/posts` | Bearer | `{title, body}` → new post |
| PUT | `/posts/{id}` | Bearer (owner) | Update a post |
| DELETE | `/posts/{id}` | Bearer (owner) | Delete a post |
| GET | `/search?q=&limit=` | – | BM25-ranked results |

Each service also shows its interactive docs (`/docs`) and `/health` inside the Docker network. To open the docs from your machine, add a `ports:` mapping to that service in `docker-compose.yml` (e.g. `"8001:8000"` for auth).

## Layout

```
docker-compose.yml       # all services, databases, Redis, gateway
gateway/nginx.conf       # routing
services/
  auth/    Dockerfile, requirements.txt, app/main.py
  posts/   Dockerfile, requirements.txt, app/main.py
  search/  Dockerfile, requirements.txt, app/main.py, app/index.py
```

## Ideas for next steps

- Tune BM25 (`k1`, `b`, title boost) or add stemming, fuzzy matching, or embedding search next to BM25.
- Persist index snapshots so startup doesn't replay the whole stream.
- Switch JWT to RS256 so posts only needs the public key.
- Add tests and a CI pipeline.
