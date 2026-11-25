"""FABRIX FastAPI application.

Run with: python -m uvicorn backend.main:app --reload --port 8000
The API lives under /api/v1; the existing static pages are served from /.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import API_PREFIX, FRONTEND_ORIGINS, ROOT
from .routers import (
    auth,
    cart,
    favorites,
    misc,
    orders,
    products,
    recommendations,
    reservations,
    reviews,
    sellers,
    users,
)
from .seed import seed_database

HTML_PAGES = [
    "index.html",
    "products.html",
    "product.html",
    "artisan.html",
    "auth.html",
    "cart.html",
    "favorites.html",
    "checkout.html",
    "confirmation.html",
    "order.html",
    "orders.html",
    "recommendations.html",
    "help.html",
    "account.html",
    "seller.html",
    "admin.html",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_database()
    yield


app = FastAPI(
    title="FABRIX API",
    version="0.1.0",
    description="Server-authoritative marketplace API for the FABRIX handmade marketplace.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        {
            "loc": list(error.get("loc", ())),
            "type": error.get("type", "validation_error"),
            "msg": str(error.get("msg", "Invalid value")),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Invalid request", "errors": errors},
    )


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "fabrix-api"}


@app.get(f"{API_PREFIX}/info", tags=["system"])
def api_info() -> dict[str, object]:
    return {
        "name": "FABRIX API",
        "version": "0.1.0",
        "prefix": API_PREFIX,
        "docs": "/docs",
    }


# API routes first.
for module in (
    auth,
    users,
    products,
    favorites,
    cart,
    reservations,
    orders,
    sellers,
    reviews,
    recommendations,
    misc,
):
    app.include_router(module.router, prefix=API_PREFIX)
for module in (sellers, reviews):
    if getattr(module, "admin_router", None):
        app.include_router(module.admin_router, prefix=API_PREFIX)
app.include_router(recommendations.admin_router, prefix=API_PREFIX)


def _serve_page(filename: str = "index.html"):
    return FileResponse(ROOT / filename)


# Static frontend support so the API can be the only server needed locally.
app.add_api_route("/", _serve_page, methods=["GET"], include_in_schema=False)
for _page in HTML_PAGES:
    app.add_api_route(
        f"/{_page}",
        lambda filename=_page: _serve_page(filename),
        methods=["GET"],
        include_in_schema=False,
    )

app.mount("/assets", StaticFiles(directory=ROOT / "assets"), name="assets")
app.mount("/css", StaticFiles(directory=ROOT / "css"), name="css")
app.mount("/js", StaticFiles(directory=ROOT / "js"), name="js")
