"""Auth service: register / login / logout / me.

Security properties:
- bcrypt password hashing (cost from BCRYPT_ROUNDS, default 12)
- short-lived HS256 JWT delivered ONLY as an httpOnly, Secure, SameSite=Strict cookie
- CSRF: signed double-submit token (random value in a readable cookie, its SHA-256 in the JWT)
- per-IP rate limiting + per-username lockout (persisted in SQLite, applies to unknown usernames too)
- constant-time-ish login: a dummy bcrypt check runs when the username does not exist
- strict input validation and a password policy
- no secrets in code: everything comes from the environment, and the service refuses weak JWT secrets
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager, closing
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .ratelimit import SlidingWindowLimiter

log = logging.getLogger("auth")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

# ---------------------------------------------------------------------------
# Configuration (environment only)
# ---------------------------------------------------------------------------
JWT_SECRET = os.environ.get("JWT_SECRET", "")
if len(JWT_SECRET.encode()) < 32:
    raise RuntimeError("JWT_SECRET must be set and at least 32 bytes long")
JWT_ISSUER = os.getenv("JWT_ISSUER", "consultancy-auth")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "consultancy-app")
JWT_TTL_MINUTES = int(os.getenv("JWT_TTL_MINUTES", "15"))
BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12"))
DB_PATH = os.getenv("DB_PATH", "/data/auth.db")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() != "false"
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
MAX_FAILED_LOGINS = int(os.getenv("MAX_FAILED_LOGINS", "5"))
LOCKOUT_MINUTES = int(os.getenv("LOCKOUT_MINUTES", "15"))

ACCESS_COOKIE = "access_token"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "x-csrf-token"

login_ip_limiter = SlidingWindowLimiter(limit=int(os.getenv("LOGIN_RATE_PER_MIN", "10")), window_s=60)
register_ip_limiter = SlidingWindowLimiter(limit=int(os.getenv("REGISTER_RATE_PER_HOUR", "20")), window_s=3600)

# A real bcrypt hash used to burn the same CPU time when a username doesn't exist.
_DUMMY_HASH = bcrypt.hashpw(secrets.token_bytes(16), bcrypt.gensalt(BCRYPT_ROUNDS))

COMMON_PASSWORDS = {
    "password1234", "123456789012", "qwertyuiop12", "letmein12345", "welcome12345",
    "administrator", "passw0rd1234", "iloveyou1234", "changeme1234", "password123!",
}


# ---------------------------------------------------------------------------
# Database (SQLite, file lives in a Docker volume)
# ---------------------------------------------------------------------------
def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=5, isolation_level=None)  # autocommit; explicit BEGIN where needed
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with closing(connect()) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at    TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS login_attempts (
                username_key  TEXT PRIMARY KEY,
                failures      INTEGER NOT NULL DEFAULT 0,
                locked_until  REAL NOT NULL DEFAULT 0
            );
            """
        )


def get_db():
    with closing(connect()) as conn:
        yield conn


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


docs = os.getenv("ENABLE_DOCS", "false").lower() == "true"
app = FastAPI(
    title="Auth Service",
    lifespan=lifespan,
    docs_url="/api/auth/docs" if docs else None,
    redoc_url=None,
    openapi_url="/api/auth/openapi.json" if docs else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # explicit allowlist, never "*" with credentials
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
    max_age=600,
)


@app.middleware("http")
async def origin_guard(request: Request, call_next):
    """Reject cross-site state-changing requests (defence in depth on top of SameSite + CSRF token)."""
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin is not None and origin not in ALLOWED_ORIGINS:
            return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
        ctype = request.headers.get("content-type", "")
        if request.url.path != "/api/auth/logout" and not ctype.startswith("application/json"):
            return JSONResponse({"detail": "Content-Type must be application/json"}, status_code=415)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


# ---------------------------------------------------------------------------
# Schemas and validation
# ---------------------------------------------------------------------------
USERNAME_RE = r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,31}$"


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    username: str = Field(min_length=3, max_length=32, pattern=USERNAME_RE)
    password: str = Field(min_length=1, max_length=128)


class Registration(Credentials):
    @field_validator("password")
    @classmethod
    def password_policy(cls, v: str, info):
        problems = password_problems(v, info.data.get("username", ""))
        if problems:
            raise ValueError("; ".join(problems))
        return v


class UserOut(BaseModel):
    id: int
    username: str
    expires_at: int | None = None


def password_problems(pw: str, username: str) -> list[str]:
    problems = []
    if len(pw) < 12:
        problems.append("at least 12 characters")
    if len(pw.encode("utf-8")) > 72:  # bcrypt only uses the first 72 bytes
        problems.append("at most 72 bytes")
    classes = sum(bool(re.search(p, pw)) for p in (r"[a-z]", r"[A-Z]", r"[0-9]", r"[^A-Za-z0-9]"))
    if classes < 3:
        problems.append("at least 3 of: lowercase, uppercase, digit, symbol")
    if username and username.lower() in pw.lower():
        problems.append("must not contain the username")
    if pw.lower() in COMMON_PASSWORDS:
        problems.append("too common")
    return problems


def client_ip(request: Request) -> str:
    # nginx is the only ingress (services publish no ports) and sets X-Real-IP.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


# ---------------------------------------------------------------------------
# Tokens and cookies
# ---------------------------------------------------------------------------
def issue_session(response: Response, user_id: int, username: str) -> int:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=JWT_TTL_MINUTES)
    csrf = secrets.token_urlsafe(32)
    claims = {
        "sub": str(user_id),
        "username": username,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": exp,
        "jti": str(uuid.uuid4()),
        "csrf": hashlib.sha256(csrf.encode()).hexdigest(),
    }
    token = jwt.encode(claims, JWT_SECRET, algorithm="HS256")
    max_age = JWT_TTL_MINUTES * 60
    common = dict(max_age=max_age, secure=COOKIE_SECURE, samesite="strict", path="/")
    response.set_cookie(ACCESS_COOKIE, token, httponly=True, **common)
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, **common)  # JS reads it, echoes it in a header
    return int(exp.timestamp())


def clear_session(response: Response) -> None:
    for name in (ACCESS_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/", secure=COOKIE_SECURE, samesite="strict")


def current_claims(request: Request) -> dict:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        return jwt.decode(
            token, JWT_SECRET, algorithms=["HS256"], audience=JWT_AUDIENCE, issuer=JWT_ISSUER,
            options={"require": ["exp", "iat", "sub", "aud", "iss", "csrf"]},
        )
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")


def require_csrf(request: Request, claims: dict) -> None:
    sent = request.headers.get(CSRF_HEADER, "")
    expected = claims.get("csrf", "")
    if not sent or not hmac.compare_digest(hashlib.sha256(sent.encode()).hexdigest(), expected):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF check failed")


# ---------------------------------------------------------------------------
# Lockout helpers (keyed by lower-cased username, whether or not the user exists)
# ---------------------------------------------------------------------------
def locked_for(db: sqlite3.Connection, key: str) -> float:
    row = db.execute("SELECT locked_until FROM login_attempts WHERE username_key = ?", (key,)).fetchone()
    return max(0.0, row["locked_until"] - time.time()) if row else 0.0


def record_failure(db: sqlite3.Connection, key: str) -> None:
    db.execute(
        "INSERT INTO login_attempts (username_key, failures) VALUES (?, 1) "
        "ON CONFLICT(username_key) DO UPDATE SET failures = failures + 1",
        (key,),
    )
    row = db.execute("SELECT failures FROM login_attempts WHERE username_key = ?", (key,)).fetchone()
    if row["failures"] >= MAX_FAILED_LOGINS:
        db.execute(
            "UPDATE login_attempts SET failures = 0, locked_until = ? WHERE username_key = ?",
            (time.time() + LOCKOUT_MINUTES * 60, key),
        )


def reset_failures(db: sqlite3.Connection, key: str) -> None:
    db.execute("DELETE FROM login_attempts WHERE username_key = ?", (key,))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED, response_model=UserOut)
def register(body: Registration, request: Request, response: Response, db: sqlite3.Connection = Depends(get_db)):
    if not register_ip_limiter.hit(client_ip(request)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many registrations, try later")
    pw_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt(BCRYPT_ROUNDS)).decode()
    try:
        cur = db.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (body.username, pw_hash, datetime.now(timezone.utc).isoformat()),
        )
    except sqlite3.IntegrityError:
        # Registration necessarily reveals that a name is taken; the per-IP limit above slows enumeration.
        raise HTTPException(status.HTTP_409_CONFLICT, "Username is not available")
    exp = issue_session(response, cur.lastrowid, body.username)
    log.info("user registered id=%s", cur.lastrowid)
    return UserOut(id=cur.lastrowid, username=body.username, expires_at=exp)


@app.post("/api/auth/login", response_model=UserOut)
def login(body: Credentials, request: Request, response: Response, db: sqlite3.Connection = Depends(get_db)):
    if not login_ip_limiter.hit(client_ip(request)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts, try again in a minute")
    key = body.username.lower()
    if locked_for(db, key) > 0:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Account temporarily locked, try again later")

    row = db.execute("SELECT id, username, password_hash FROM users WHERE username = ?", (body.username,)).fetchone()
    pw = body.password.encode()[:72]
    if row is None:
        bcrypt.checkpw(pw, _DUMMY_HASH)  # same cost as a real check, so timing doesn't reveal existence
        ok = False
    else:
        ok = bcrypt.checkpw(pw, row["password_hash"].encode())

    if not ok:
        record_failure(db, key)
        log.warning("failed login ip=%s", client_ip(request))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")

    reset_failures(db, key)
    exp = issue_session(response, row["id"], row["username"])
    return UserOut(id=row["id"], username=row["username"], expires_at=exp)


@app.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request):
    # Logout is idempotent; if a valid session exists we still demand the CSRF header.
    try:
        claims = current_claims(request)
        require_csrf(request, claims)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            raise
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session(resp)
    return resp


@app.get("/api/auth/me", response_model=UserOut)
def me(request: Request):
    claims = current_claims(request)
    return UserOut(id=int(claims["sub"]), username=claims["username"], expires_at=int(claims["exp"]))
