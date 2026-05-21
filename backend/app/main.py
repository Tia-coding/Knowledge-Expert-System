from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config.settings import get_settings
from app.database.init_db import init_db
from app.routes import auth, documents, rag, system
from app.utils.logging import configure_logging


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

# Serve frontend files
app.mount(
    "/",
    StaticFiles(directory="frontend", html=True),
    name="frontend"
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