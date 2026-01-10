"""
Clash IP Checker - Web Configuration Interface
FastAPI backend with SSE progress and REST API
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from routers.api import router as api_router
from routers.views import router as views_router

from contextlib import asynccontextmanager
from state import state

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown
    print("[Web] Shutting down, cleaning up resources...")
    await state.checker.stop()

app = FastAPI(title="Clash IP Checker", lifespan=lifespan)

# Mount supporting static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Ensure exports directory
exports_dir = "exports"
os.makedirs(exports_dir, exist_ok=True)
app.mount("/exports", StaticFiles(directory=exports_dir), name="exports")

# Include Routers
app.include_router(views_router)
app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)
