import asyncio
import logging
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import jwt
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app import database
from app.config import settings
from app.schemas import HomePlannerRequest, JewelryPlannerRequest, LoginRequest, PartyPlannerRequest, RegisterRequest
from app.security import create_access_token, decode_access_token, hash_password, verify_password
from app.services.recommendations import recommendation_service


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token", auto_error=False)
PLANNER_LABELS = {"home": "Home Interior", "party": "Party Planning", "jewelry": "Jewelry"}
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.app_env.lower() == "production" and (
        settings.app_secret_key in {"local-development-only-change-me", "replace-this-with-a-long-random-secret-before-deployment"}
        or len(settings.app_secret_key) < 32
    ):
        raise RuntimeError("Set APP_SECRET_KEY to a private random value before production startup.")
    database.init_db()
    database.cleanup_expired_tokens(int(time.time()))
    yield


app = FastAPI(title="PocketSmart AI", version="1.0.0", lifespan=lifespan)
logger = logging.getLogger("pocketsmart")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _set_session_cookies(response: JSONResponse, user_id: int) -> None:
    token, _ = create_access_token(str(user_id))
    cookie_args = {
        "max_age": settings.session_ttl_minutes * 60,
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "path": "/",
    }
    response.set_cookie("pocketsmart_session", token, httponly=True, **cookie_args)
    response.set_cookie("pocketsmart_csrf", secrets.token_urlsafe(24), httponly=False, **cookie_args)


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {key: user[key] for key in ("id", "username", "email", "created_at") if key in user}


async def get_current_user(
    request: Request,
    bearer_token: str | None = Depends(oauth2_scheme),
) -> dict[str, Any]:
    cookie_token = request.cookies.get("pocketsmart_session")
    token = bearer_token or cookie_token
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in to continue.")
    try:
        claims = decode_access_token(token)
        token_id = claims.get("jti")
        user_id = int(claims["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session has expired. Please sign in again.")
    if not token_id or database.is_token_revoked(str(token_id)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="This session has ended. Please sign in again.")
    if cookie_token and not bearer_token and request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf_cookie = request.cookies.get("pocketsmart_csrf", "")
        csrf_header = request.headers.get("x-csrf-token", "")
        if not csrf_cookie or not secrets.compare_digest(csrf_cookie, csrf_header):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="The request security token is missing or invalid. Refresh the page and try again.")
    user = database.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="This account is no longer available.")
    return user


async def get_optional_user(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get("pocketsmart_session")
    if not token:
        return None
    try:
        claims = decode_access_token(token)
        if database.is_token_revoked(str(claims.get("jti", ""))):
            return None
        return database.get_user_by_id(int(claims["sub"]))
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        return None


def _page(name: str, request: Request, user: dict[str, Any] | None = None, **context: Any) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name=name,
        context={"user": _public_user(user) if user else None, "planner_labels": PLANNER_LABELS, **context},
    )


@app.get("/", response_class=HTMLResponse, name="home_page")
async def home_page(request: Request):
    return _page("home.html", request, await get_optional_user(request))


@app.get("/register", response_class=HTMLResponse, name="register_page")
async def register_page(request: Request):
    user = await get_optional_user(request)
    if user:
        return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return _page("auth.html", request, mode="register")


@app.get("/login", response_class=HTMLResponse, name="login_page")
async def login_page(request: Request):
    user = await get_optional_user(request)
    if user:
        return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return _page("auth.html", request, mode="login")


@app.get("/dashboard", response_class=HTMLResponse, name="dashboard_page")
async def dashboard_page(request: Request):
    user = await get_optional_user(request)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return _page("dashboard.html", request, user)


@app.get("/planner/{planner_type}", response_class=HTMLResponse, name="planner_page")
async def planner_page(request: Request, planner_type: str):
    if planner_type not in PLANNER_LABELS:
        raise HTTPException(status_code=404, detail="Planner not found.")
    user = await get_optional_user(request)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return _page("planner.html", request, user, planner_type=planner_type, planner_label=PLANNER_LABELS[planner_type])


@app.get("/history", response_class=HTMLResponse, name="history_page")
async def history_page(request: Request):
    if "application/json" in request.headers.get("accept", ""):
        user = await get_optional_user(request)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in to continue.")
        return JSONResponse(content=_history_payload(int(user["id"])))
    user = await get_optional_user(request)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return _page("history.html", request, user)


@app.get("/testimonials", response_class=HTMLResponse, name="testimonials_page")
async def testimonials_page(request: Request):
    return _page("testimonials.html", request, await get_optional_user(request))


@app.get("/health")
async def health():
    return {"status": "ok", "gemini_configured": bool(settings.gemini_api_key), "model": settings.gemini_model}


@app.get("/startup")
async def startup_status():
    return {"status": "ready", "database": "sqlite", "recommendation_mode": "gemini" if settings.gemini_api_key else "local fallback"}


@app.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest):
    try:
        user = database.create_user(payload.username, payload.email, hash_password(payload.password))
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That username or email is already registered.")
    response = JSONResponse(status_code=status.HTTP_201_CREATED, content={"user": _public_user(user), "message": "Your account is ready."})
    _set_session_cookies(response, int(user["id"]))
    return response


@app.post("/login")
async def login(payload: LoginRequest):
    user = database.get_user_by_username(payload.username)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="The username or password is incorrect.")
    response = JSONResponse(content={"user": _public_user(user), "message": "You are signed in."})
    _set_session_cookies(response, int(user["id"]))
    return response


@app.post("/token")
async def issue_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = database.get_user_by_username(form_data.username)
    if not user or not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="The username or password is incorrect.", headers={"WWW-Authenticate": "Bearer"})
    token, _ = create_access_token(str(user["id"]))
    return {"access_token": token, "token_type": "bearer", "expires_in": settings.session_ttl_minutes * 60}


@app.post("/logout")
async def logout(request: Request, user: dict[str, Any] = Depends(get_current_user), bearer_token: str | None = Depends(oauth2_scheme)):
    token = bearer_token or request.cookies.get("pocketsmart_session")
    if token:
        try:
            claims = decode_access_token(token)
            database.revoke_token(str(claims["jti"]), int(claims["exp"]))
        except (jwt.InvalidTokenError, KeyError, ValueError):
            pass
    response = JSONResponse(content={"message": "You have signed out."})
    response.delete_cookie("pocketsmart_session", path="/")
    response.delete_cookie("pocketsmart_csrf", path="/")
    return response


@app.get("/session-info")
async def session_info(request: Request, user: dict[str, Any] = Depends(get_current_user)):
    token = request.cookies.get("pocketsmart_session") if request else None
    expires_at = None
    if token:
        try:
            expires_at = decode_access_token(token).get("exp")
        except jwt.InvalidTokenError:
            pass
    return {"authenticated": True, "user": _public_user(user), "expires_at": expires_at}


@app.get("/session-data")
async def session_data(user: dict[str, Any] = Depends(get_current_user)):
    recent = database.list_recommendations(int(user["id"]), limit=5)
    return {
        "user": _public_user(user),
        "recommendation_count": database.recommendation_count(int(user["id"])),
        "recent_recommendations": [
            {"id": row["id"], "planner_type": row["planner_type"], "created_at": row["created_at"], "title": row["result"].get("title", "Saved plan")}
            for row in recent
        ],
    }


async def _save_and_return(
    planner_type: str,
    payload: dict[str, Any],
    user: dict[str, Any],
    image_bytes: bytes | None = None,
    image_mime_type: str | None = None,
):
    plan = await asyncio.to_thread(recommendation_service.generate, planner_type, payload, image_bytes, image_mime_type)
    source = str(plan.pop("source", "local"))
    record = database.add_recommendation(int(user["id"]), planner_type, payload, plan, source)
    return {"id": record["id"], "created_at": record["created_at"], "planner_type": planner_type, "source": source, "plan": plan}


@app.post("/generate-home")
async def generate_home(payload: HomePlannerRequest, user: dict[str, Any] = Depends(get_current_user)):
    return await _save_and_return("home", payload.model_dump(), user)


@app.post("/generate-party")
async def generate_party(payload: PartyPlannerRequest, user: dict[str, Any] = Depends(get_current_user)):
    return await _save_and_return("party", payload.model_dump(), user)


@app.post("/generate-jewelry")
async def generate_jewelry(
    budget: float = Form(...),
    occasion: str = Form(...),
    style: str = Form(...),
    outfit_description: str = Form(default=""),
    outfit_image: UploadFile | None = File(default=None),
    user: dict[str, Any] = Depends(get_current_user),
):
    try:
        payload = JewelryPlannerRequest.model_validate({
            "budget": budget,
            "occasion": occasion,
            "style": style,
            "outfit_description": outfit_description,
        }).model_dump()
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_context=False))
    image_bytes = None
    image_mime_type = None
    if outfit_image and outfit_image.filename:
        image_mime_type = (outfit_image.content_type or "").lower()
        if image_mime_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=415, detail="Upload a JPG, PNG, or WebP image.")
        image_bytes = await outfit_image.read(settings.max_upload_mb * 1024 * 1024 + 1)
        if len(image_bytes) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"The image must be smaller than {settings.max_upload_mb} MB.")
        if not _looks_like_image(image_bytes, image_mime_type):
            raise HTTPException(status_code=415, detail="The uploaded file does not match its image type.")
        payload["has_outfit_image"] = True
    if outfit_image:
        await outfit_image.close()
    return await _save_and_return("jewelry", payload, user, image_bytes, image_mime_type)


def _looks_like_image(content: bytes, mime_type: str) -> bool:
    if mime_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if mime_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if mime_type == "image/webp":
        return len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    return False


@app.get("/api/history")
async def api_history(user: dict[str, Any] = Depends(get_current_user)):
    return _history_payload(int(user["id"]))


def _history_payload(user_id: int) -> dict[str, Any]:
    rows = database.list_recommendations(user_id)
    return {
        "items": [
            {
                "id": row["id"],
                "planner_type": row["planner_type"],
                "planner_label": PLANNER_LABELS.get(row["planner_type"], row["planner_type"].title()),
                "title": row["result"].get("title", "Saved plan"),
                "budget": row["result"].get("budget", row["request"].get("budget", 0)),
                "total_estimated": row["result"].get("total_estimated", 0),
                "created_at": row["created_at"],
                "source": row["source"],
            }
            for row in rows
        ]
    }


@app.get("/recommendations-details/{recommendation_id}")
async def recommendation_details(recommendation_id: int, user: dict[str, Any] = Depends(get_current_user)):
    row = database.get_recommendation(int(user["id"]), recommendation_id)
    if not row:
        raise HTTPException(status_code=404, detail="Saved recommendation not found.")
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "planner_type": row["planner_type"],
        "input": row["request"],
        "plan": row["result"],
        "source": row["source"],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=settings.app_env.lower() == "development")
