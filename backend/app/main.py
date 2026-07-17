from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config.settings import get_settings
from app.database.init_db import init_db
#Added public_chat
from app.routes import auth, documents, rag, system, public_chat
from app.utils.logging import configure_logging
#Added path
from pathlib import Path

import logging

logging.getLogger(
    "chromadb.segment.impl.vector.local_persistent_hnsw"
).setLevel(logging.ERROR)

logging.getLogger(
    "chromadb.segment.impl.metadata.sqlite"
).setLevel(logging.ERROR)

logging.getLogger(
    "chromadb.telemetry.product.posthog"
).setLevel(logging.ERROR)


# Initialize settings and logging
settings = get_settings()
configure_logging()

# Initialize database
init_db()

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(auth.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(rag.router, prefix="/api")
app.include_router(system.router, prefix="/api")
#Added public_chat
app.include_router(public_chat.router, prefix="/api")

# Added Serve frontend files
BASE_DIR = Path(__file__).resolve().parent.parent.parent

FRONTEND_DIR = BASE_DIR / "frontend"

print("Frontend directory:", FRONTEND_DIR)

app.mount(
    "/",
    StaticFiles(
        directory=str(FRONTEND_DIR),
        html=True,
    ),
    name="frontend",
)

















# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.staticfiles import StaticFiles
# from app.config.settings import get_settings
# from app.database.init_db import init_db
# from app.routes import auth, documents, rag, system
# from app.utils.logging import configure_logging


# settings = get_settings()
# configure_logging()
# init_db()

# app = FastAPI(title=settings.app_name, version="1.0.0")
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# app.include_router(auth.router, prefix="/api")
# app.include_router(documents.router, prefix="/api")
# app.include_router(rag.router, prefix="/api")
# app.include_router(system.router, prefix="/api")
# app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")