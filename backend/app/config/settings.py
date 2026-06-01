from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    # =========================================================
    # APPLICATION
    # =========================================================

    app_name: str = (
        "NRSC Documents Knowledge Expert System"
    )

    offline_storage_dir: str = "./backend/offline_storage/dspace_documents"

    dspace_base_url: str = ""

    dspace_timeout: int = 10
    # =========================================================
    # SECURITY
    # =========================================================

    secret_key: str = (
        "change-this-secret-key"
    )

    algorithm: str = "HS256"

    access_token_expire_minutes: int = 480

    # =========================================================
    # DATABASE
    # =========================================================

    database_url: str = (
        "sqlite:///./backend/nrsc.db"
    )

    # =========================================================
    # STORAGE DIRECTORIES
    # =========================================================

    upload_dir: str = "./backend/uploads"

    chroma_dir: str = "./backend/chroma_db"

    log_dir: str = "./backend/logs"

    # =========================================================
    # EMBEDDING MODEL
    # =========================================================

    embedding_model: str = (
        "BAAI/bge-base-en-v1.5"
    )

    # =========================================================
    # OLLAMA
    # =========================================================

    ollama_base_url: str = (
        "http://localhost:11434"
    )

    ollama_model: str = "llama3.2:3b"

    # =========================================================
    # RAG SETTINGS
    # =========================================================

    rag_top_k: int = 8

    chunk_size: int = 1400

    chunk_overlap: int = 250

    # =========================================================
    # FILE LIMITS
    # =========================================================

    max_upload_mb: int = 100

    # =========================================================
    # PYDANTIC CONFIG
    # =========================================================

    class Config:

        env_file = "./backend/.env"

        env_file_encoding = "utf-8"

        case_sensitive = False

    # =========================================================
    # ENSURE REQUIRED DIRECTORIES
    # =========================================================

    def ensure_dirs(self) -> None:

        for value in (

            self.upload_dir,

            self.chroma_dir,

            self.log_dir,

        ):

            try:

                Path(value).mkdir(

                    parents=True,

                    exist_ok=True,

                )

            except Exception as e:

                raise RuntimeError(

                    f"Failed to create directory "
                    f"{value}: {str(e)}"

                )

    # =========================================================
    # VALIDATE IMPORTANT SETTINGS
    # =========================================================

    def validate_settings(self) -> None:

        if (
            not self.secret_key
            or self.secret_key
            == "change-this-secret-key"
        ):

            print(
                "\nWARNING: Using default secret key."
                "\nSet SECRET_KEY in .env "
                "for production.\n"
            )

        if self.max_upload_mb <= 0:

            raise ValueError(
                "max_upload_mb must be positive"
            )

        if self.chunk_overlap >= self.chunk_size:

            raise ValueError(
                "chunk_overlap must be "
                "smaller than chunk_size"
            )

    # =========================================================
    # INITIALIZATION
    # =========================================================

    def initialize(self) -> None:

        self.ensure_dirs()

        self.validate_settings()


# =============================================================
# CACHED SETTINGS INSTANCE
# =============================================================

@lru_cache
def get_settings() -> Settings:

    settings = Settings()

    settings.initialize()

    return settings
