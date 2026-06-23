from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    app_name: str = (
        "NRSC Documents Knowledge Expert System"
    )

    offline_storage_dir: str = "./backend/offline_storage/dspace_documents"

    dspace_base_url: str = ""

    dspace_timeout: int = 10

    secret_key: str = (
        "change-this-secret-key"
    )

    algorithm: str = "HS256"

    access_token_expire_minutes: int = 480

    database_url: str = (
        "sqlite:///./backend/nrsc.db"
    )

    upload_dir: str = "./backend/uploads"

    chroma_dir: str = "./backend/chroma_db"

    log_dir: str = "./backend/logs"

    embedding_model: str = "BAAI/bge-base-en-v1.5"

    llm_provider: str = "ollama"

    llm_model: str = "llama3.2:3b"

    llm_base_url: str = "http://localhost:11434"

    # VLLM SETTINGS

    # llm_provider: str = "vllm"

    # llm_model: str = "meta-llama/Llama-3.2-3B-Instruct"

    # llm_base_url: str = "http://localhost:8000/v1"

    rag_top_k: int = 8

    chunk_size: int = 1200

    chunk_overlap: int = 250

    max_upload_mb: int = 100

    class Config:

        env_file = "./backend/.env"

        env_file_encoding = "utf-8"

        case_sensitive = False

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

    def initialize(self) -> None:

        self.ensure_dirs()

        self.validate_settings()

@lru_cache
def get_settings() -> Settings:

    settings = Settings()

    settings.initialize()

    return settings
