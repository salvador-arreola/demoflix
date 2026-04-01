import json
import os
import re
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from google.cloud import storage
from google.cloud.exceptions import NotFound

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DEMO_DIR = STATIC_DIR / "demo"
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", str(PROJECT_ROOT / "data"))).resolve()
LOCAL_POSTERS_DIR = DATA_DIR / "posters"
LOCAL_CATALOG_PATH = DATA_DIR / "catalog.json"

CATALOG_BLOB = "catalog.json"
POSTER_PREFIX = "posters/"
MAX_POSTER_BYTES = 5 * 1024 * 1024
ALLOWED_CONTENT_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/gif"}
)
EXT_FOR_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

_bucket_name = os.environ.get("GCS_BUCKET_NAME", "").strip()
_use_gcs = bool(_bucket_name)

_catalog_lock = threading.Lock()
_storage_client: storage.Client | None = None

_DEMO_EXT = ".jpg"
# Public-domain NASA imagery; see ATTRIBUTION.md
_DEMO_MOVIES: tuple[tuple[str, str], ...] = (
    ("cloud-atlas", "Orion Nebula"),
    ("the-pipeline", "Black Hole Shadow"),
    ("midnight-region", "Jupiter"),
    ("byte-and-soul", "Deep Field"),
)


def _ensure_demo_dir() -> None:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)


def _demo_rows() -> list[dict]:
    return [
        {
            "id": f"demo-{slug}",
            "title": title,
            "poster_url": f"/static/demo/{slug}{_DEMO_EXT}",
        }
        for slug, title in _DEMO_MOVIES
    ]


def _client() -> storage.Client:
    global _storage_client
    if _storage_client is None:
        _storage_client = storage.Client()
    return _storage_client


def _bucket():
    if not _bucket_name:
        raise HTTPException(
            status_code=503,
            detail="GCS_BUCKET_NAME is not configured",
        )
    return _client().bucket(_bucket_name)


def _gcs_poster_url(object_name: str) -> str:
    return (
        f"https://storage.googleapis.com/{_bucket_name}/"
        f"{quote(object_name, safe='/')}"
    )


def _load_gcs_user_catalog() -> list:
    bucket = _bucket()
    blob = bucket.blob(CATALOG_BLOB)
    try:
        data = blob.download_as_text()
    except NotFound:
        return []
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _save_gcs_user_catalog(movies: list) -> None:
    bucket = _bucket()
    blob = bucket.blob(CATALOG_BLOB)
    blob.upload_from_string(
        json.dumps(movies, ensure_ascii=False, indent=2),
        content_type="application/json",
    )


def _load_local_user_catalog() -> list:
    if not LOCAL_CATALOG_PATH.is_file():
        return []
    try:
        parsed = json.loads(LOCAL_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _save_local_user_catalog(movies: list) -> None:
    LOCAL_POSTERS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_CATALOG_PATH.write_text(
        json.dumps(movies, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _sanitize_title(title: str) -> str:
    t = (title or "").strip()
    if not t or len(t) > 200:
        raise HTTPException(status_code=400, detail="Invalid title")
    return t


def _safe_ext(filename: str | None, content_type: str | None) -> str:
    if content_type in EXT_FOR_TYPE:
        return EXT_FOR_TYPE[content_type]
    if filename:
        m = re.search(r"\.(jpe?g|png|webp|gif)$", filename.lower())
        if m:
            return "." + m.group(1).replace("jpeg", "jpg").replace("jpe", "jpg")
    raise HTTPException(
        status_code=400,
        detail="Unsupported format (use JPEG, PNG, WebP, or GIF)",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_demo_dir()
    if not _use_gcs:
        LOCAL_POSTERS_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Demo Netflix GCE + GCS", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "storage": "gcs" if _use_gcs else "local",
        "bucket": _bucket_name or None,
        "data_dir": str(DATA_DIR) if not _use_gcs else None,
    }


@app.get("/api/movies")
def list_movies():
    demos = _demo_rows()
    with _catalog_lock:
        if _use_gcs:
            raw = _load_gcs_user_catalog()
        else:
            raw = _load_local_user_catalog()
    user_out = []
    for m in raw:
        if not isinstance(m, dict):
            continue
        bid = m.get("id")
        title = m.get("title")
        if not bid or not title:
            continue
        if _use_gcs:
            obj = m.get("poster_object")
            if not obj:
                continue
            user_out.append(
                {
                    "id": bid,
                    "title": title,
                    "poster_url": _gcs_poster_url(obj),
                }
            )
        else:
            fn = m.get("poster_file")
            if not fn:
                continue
            user_out.append(
                {
                    "id": bid,
                    "title": title,
                    "poster_url": f"/uploads/{quote(fn, safe='')}",
                }
            )
    return demos + user_out


@app.post("/api/movies")
async def create_movie(
    title: str = Form(...),
    poster: UploadFile = File(...),
):
    _sanitize_title(title)
    ct = poster.content_type or ""
    if ct not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Image type not allowed")
    body = await poster.read()
    if len(body) > MAX_POSTER_BYTES:
        raise HTTPException(
            status_code=400,
            detail="Image too large (max 5 MB)",
        )
    ext = _safe_ext(poster.filename, ct)
    movie_id = str(uuid.uuid4())

    if _use_gcs:
        object_name = f"{POSTER_PREFIX}{movie_id}{ext}"
        bucket = _bucket()
        bucket.blob(object_name).upload_from_string(body, content_type=ct)
        entry = {
            "id": movie_id,
            "title": title.strip(),
            "poster_object": object_name,
        }
        with _catalog_lock:
            catalog = _load_gcs_user_catalog()
            catalog.append(entry)
            _save_gcs_user_catalog(catalog)
        poster_url = _gcs_poster_url(object_name)
    else:
        LOCAL_POSTERS_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{movie_id}{ext}"
        (LOCAL_POSTERS_DIR / filename).write_bytes(body)
        entry = {
            "id": movie_id,
            "title": title.strip(),
            "poster_file": filename,
        }
        with _catalog_lock:
            catalog = _load_local_user_catalog()
            catalog.append(entry)
            _save_local_user_catalog(catalog)
        poster_url = f"/uploads/{quote(filename, safe='')}"

    return JSONResponse(
        status_code=201,
        content={
            "id": movie_id,
            "title": entry["title"],
            "poster_url": poster_url,
        },
    )


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
if not _use_gcs:
    LOCAL_POSTERS_DIR.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/uploads",
        StaticFiles(directory=str(LOCAL_POSTERS_DIR)),
        name="uploads",
    )


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
