"""FastAPI application factory: request guard, API routers, static SPA."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import APP_ID, __version__
from .api import ROUTERS
from .config import Config
from .errors import Conflict, LumiereError, NotFound, Refused
from .guard import install_guard
from .hoard_link import family
from .services import Services

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _body(error: Exception, status: int) -> JSONResponse:
    payload = {"error": str(error)}
    code = getattr(error, "code", None)
    if code:
        payload["code"] = code
    return JSONResponse(payload, status_code=status)


def create_app(config: Config | None = None, services: Services | None = None) -> FastAPI:
    """``services`` lets tests inject a pre-built instance (fake link, fake image studio)."""
    config = config or (services.config if services else Config.from_env())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        svc = services or Services(config)
        app.state.services = svc
        svc.start()
        logging.getLogger("lumiere").info("Lumière's Hoard %s — data in %s", __version__, config.data_dir)
        try:
            yield
        finally:
            svc.stop()

    app = FastAPI(title="Lumière's Hoard", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.config = config
    family.configure(APP_ID, str(config.data_dir), token_file=str(config.token_path))

    install_guard(app, config.allowed_hosts)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        return JSONResponse({"error": str(exc.detail)}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        issues = "; ".join(f"{'.'.join(str(p) for p in e['loc'] if p != 'body') or 'input'}: {e['msg']}" for e in exc.errors())
        return JSONResponse({"error": issues}, status_code=400)

    @app.exception_handler(ValidationError)
    async def model_error(_: Request, exc: ValidationError):
        issues = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'input'}: {e['msg']}" for e in exc.errors())
        return JSONResponse({"error": issues}, status_code=400)

    @app.exception_handler(Refused)
    async def refused(_: Request, exc: Refused):
        payload = {"error": str(exc), "code": getattr(exc, "code", None) or "refused"}
        return JSONResponse(payload, status_code=403)

    @app.exception_handler(Conflict)
    async def conflict(_: Request, exc: Conflict):
        return _body(exc, 409)

    @app.exception_handler(LumiereError)
    async def bad_request(_: Request, exc: LumiereError):
        return _body(exc, 400)

    @app.exception_handler(NotFound)
    async def not_found(_: Request, exc: NotFound):
        return _body(exc, 404)

    @app.exception_handler(KeyError)
    async def unknown(_: Request, exc: KeyError):
        return JSONResponse({"error": str(exc.args[0]) if exc.args else "Not found."}, status_code=404)

    for router in ROUTERS:
        app.include_router(router)

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"error": "Not found."}, status_code=404)
        static = _static_dir()
        candidate = (static / path).resolve() if path else None
        if candidate and candidate.is_file() and static.resolve() in candidate.parents:
            return FileResponse(candidate)
        index = static / "index.html"
        if index.is_file():
            return FileResponse(index)
        return JSONResponse({"error": "The client is not built yet: run `npm install && npm run build`."}, status_code=503)

    return app


def _static_dir() -> Path:
    return STATIC_DIR
