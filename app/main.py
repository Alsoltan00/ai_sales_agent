from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from app.core.config import settings
import os

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION
)

# Middleware
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Static files & Templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Import routers (To be created)
# from app.routers import auth, admin, stores, whatsapp, sync

# app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
# app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
# app.include_router(stores.router, prefix="/api/stores", tags=["Stores"])

@app.get("/")
async def root():
    return RedirectResponse(url="/admin")

@app.on_event("startup")
async def startup():
    print(f"[+] {settings.PROJECT_NAME} is starting up...")
    # Initialize DB from our core
    # await init_db()
