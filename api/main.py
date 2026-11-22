"""
Powder Flowability Prediction API.

/classify prefers the deterministic pharmacopoeial calculation and falls back
to a model only when tapped density is absent. The response always says which.

Run: python -m uvicorn api.main:app --port 8000
"""
from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError

from api.db.session import build_engine, build_session_factory, init_db
from api.billing import RazorpayClient
from api.media import LocalStorage, S3Storage
from api.routers import (admin, audit, auth, billing, classify, predictions, profile, samples, site,
                         system, users)
from src.config import ROOT, Settings, get_settings
from src.models.registry import load_bundles

log = logging.getLogger("powderflow.api")
WEB_DIR = ROOT / "app" / "dist"
# Razorpay Checkout loads its script and opens its payment form in a frame.
_CSP = ("default-src 'self'; script-src 'self' https://checkout.razorpay.com; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://*.razorpay.com; "
        "connect-src 'self' https://api.razorpay.com https://lumberjack.razorpay.com; "
        "frame-src https://api.razorpay.com https://checkout.razorpay.com; font-src 'self'; "
        "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
_ADMIN_CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
              "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
              "form-action 'self'; frame-ancestors 'none'")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    settings.require_secret()
    init_db(app.state.engine)
    app.state.bundles, app.state.training_ranges = load_bundles(settings.model_dir,
                                                                settings.model_version)
    if not app.state.bundles:
        log.warning("No models loaded. The exact (bulk + tapped) path still works.")
    yield
    app.state.engine.dispose()


def _register_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        # Pydantic's default echoes submitted values, which would include passwords.
        detail = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                  for e in exc.errors()]
        return JSONResponse({"detail": detail}, status.HTTP_422_UNPROCESSABLE_ENTITY)

    @app.exception_handler(IntegrityError)
    async def integrity_error(_request: Request, _exc: IntegrityError):
        return JSONResponse({"detail": "The request conflicts with an existing record."},
                            status.HTTP_409_CONFLICT)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", "unknown")
        log.error("Unhandled error [%s] %s %s", request_id, request.method, request.url.path,
                  exc_info=exc)
        return JSONResponse({"detail": "Internal server error", "request_id": request_id},
                            status.HTTP_500_INTERNAL_SERVER_ERROR)


UPLOAD_PATHS = {"/profile/me/photo", "/site/photos"}


def _body_error(request: Request, limit: int) -> JSONResponse | None:
    if request.method not in {"POST", "PUT", "PATCH"}:
        return None
    if "transfer-encoding" in request.headers:
        return JSONResponse({"detail": "Content-Length is required."},
                            status.HTTP_411_LENGTH_REQUIRED)
    raw = request.headers.get("content-length", "0")
    if not raw.isascii() or not raw.isdigit():
        return JSONResponse({"detail": "Invalid Content-Length."}, status.HTTP_400_BAD_REQUEST)
    if int(raw) > limit:
        return JSONResponse({"detail": "Request body too large."},
                            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    return None


def _mount_frontend(app: FastAPI, web_dir: Path) -> None:
    """Serve the built frontend from this process, so no second cloud service is needed."""
    index = web_dir / "index.html"
    if not index.is_file():
        log.info("Frontend build not found at %s; serving the API only.", web_dir)
        return

    @app.get("/", include_in_schema=False)
    def frontend():
        return FileResponse(index, media_type="text/html", headers={
            "Content-Security-Policy": _CSP, "Cache-Control": "no-cache"})

    admin_index = web_dir / "admin.html"
    if admin_index.is_file():
        @app.get("/admin", include_in_schema=False)
        def admin_panel():
            return FileResponse(admin_index, media_type="text/html", headers={
                "Content-Security-Policy": _ADMIN_CSP, "Cache-Control": "no-cache"})

    # Fixed, known icon files only; nothing else from the build root is exposed.
    for name, media_type in (("favicon.png", "image/png"), ("favicon.svg", "image/svg+xml"),
                             ("apple-touch-icon.png", "image/png")):
        icon = web_dir / name
        if icon.is_file():
            def serve(path=icon, kind=media_type):
                return FileResponse(path, media_type=kind,
                                    headers={"Cache-Control": "public, max-age=86400"})
            app.add_api_route(f"/{name}", serve, methods=["GET"], include_in_schema=False)

    if (web_dir / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=web_dir / "assets"), name="assets")


def create_app(settings: Settings | None = None, web_dir: Path = WEB_DIR) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="Powder Flowability Prediction API", version="2.0.0", lifespan=lifespan,
        description=("Uses the exact USP <1174> calculation when bulk and tapped density are "
                     "available, and a leave-one-material-out validated screening model "
                     "only when they are not."),
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings
    app.state.engine = build_engine(settings.database_url)
    app.state.session_factory = build_session_factory(app.state.engine)
    app.state.bundles = {}
    app.state.training_ranges = {}
    app.state.razorpay = (RazorpayClient(settings.razorpay_key_id, settings.razorpay_key_secret)
                          if settings.billing_enabled else None)
    app.state.storage = (S3Storage(settings.s3_bucket, settings.aws_region) if settings.s3_bucket
                         else LocalStorage(settings.upload_dir or ROOT / "data" / "app" / "uploads"))

    @app.middleware("http")
    async def request_guard(request: Request, call_next):
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        limit = (settings.max_upload_bytes if request.url.path in UPLOAD_PATHS
                 else settings.max_body_bytes)
        response = _body_error(request, limit) or await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/assets/") and response.status_code == 200:
            # Vite puts a content hash in each filename, so these never go stale.
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.add_middleware(GZipMiddleware, minimum_size=1024)
    # Added last so it is outermost and error responses also carry CORS headers.
    app.add_middleware(
        CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"], expose_headers=["X-Request-ID"],
    )
    _register_handlers(app)
    for module in (system, auth, users, classify, samples, predictions, audit, billing, admin,
                   profile, site):
        app.include_router(module.router)
    _mount_frontend(app, web_dir)
    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
