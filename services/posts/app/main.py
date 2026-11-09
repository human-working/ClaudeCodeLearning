"""Posts service: CRUD for posts. Publishes post events to a Redis stream for the search service."""
import os
from contextlib import asynccontextmanager
from datetime import datetime

import jwt
import redis
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

DATABASE_URL = os.environ["DATABASE_URL"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ISSUER = os.getenv("JWT_ISSUER", "auth-service")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
EVENTS_STREAM = os.getenv("EVENTS_STREAM", "posts.events")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
events = redis.Redis.from_url(REDIS_URL, decode_responses=True)


class Base(DeclarativeBase):
    pass


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    author_id: Mapped[int] = mapped_column(index=True)
    author_username: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Posts Service", lifespan=lifespan)
bearer = HTTPBearer()


def get_db():
    with SessionLocal() as db:
        yield db


class CurrentUser(BaseModel):
    id: int
    username: str


def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> CurrentUser:
    """Verify the JWT issued by the auth service (shared HS256 secret, no network call needed)."""
    try:
        claims = jwt.decode(creds.credentials, JWT_SECRET, algorithms=["HS256"], issuer=JWT_ISSUER)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return CurrentUser(id=int(claims["sub"]), username=claims["username"])


class PostIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20_000)


class PostOut(BaseModel):
    id: int
    title: str
    body: str
    author_id: int
    author_username: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


def publish(event_type: str, post: Post) -> None:
    fields = {"type": event_type, "id": str(post.id)}
    if event_type != "post.deleted":
        fields.update(title=post.title, body=post.body, author=post.author_username)
    events.xadd(EVENTS_STREAM, fields)


def get_owned_post(post_id: int, user: CurrentUser, db: Session) -> Post:
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    if post.author_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only modify your own posts")
    return post


@app.get("/health")
def health():
    return {"status": "ok", "service": "posts"}


@app.get("/posts", response_model=list[PostOut])
def list_posts(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    author: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(Post).order_by(Post.created_at.desc()).limit(limit).offset(offset)
    if author:
        stmt = stmt.where(Post.author_username == author)
    return db.scalars(stmt).all()


@app.get("/posts/{post_id}", response_model=PostOut)
def get_post(post_id: int, db: Session = Depends(get_db)):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    return post


@app.post("/posts", response_model=PostOut, status_code=status.HTTP_201_CREATED)
def create_post(body: PostIn, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    post = Post(title=body.title, body=body.body, author_id=user.id, author_username=user.username)
    db.add(post)
    db.commit()
    db.refresh(post)
    publish("post.created", post)
    return post


@app.put("/posts/{post_id}", response_model=PostOut)
def update_post(
    post_id: int, body: PostIn, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)
):
    post = get_owned_post(post_id, user, db)
    post.title, post.body = body.title, body.body
    db.commit()
    db.refresh(post)
    publish("post.updated", post)
    return post


@app.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(post_id: int, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    post = get_owned_post(post_id, user, db)
    db.delete(post)
    db.commit()
    publish("post.deleted", post)
