import os
from pydantic_settings import BaseSettings
from pydantic import ConfigDict, model_validator

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_ENV_FILE = os.path.join(_PROJECT_ROOT, ".env")


class Settings(BaseSettings):
    groq_api_key: str
    llm_model: str = "llama-3.3-70b-versatile"
    chroma_db_path: str = "storage/chroma_db"
    collection_name: str = "hotel_docs"
    data_folder: str = "storage/data"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    top_k_retrieval: int = 5
    database_url: str = "sqlite:///storage/hotel.db"
    fernet_key: str = ""
    log_level: str = "INFO"

    model_config = ConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
    )

    @model_validator(mode="after")
    def _resolve_paths(self) -> "Settings":
        def abs_path(p: str) -> str:
            return p if os.path.isabs(p) else os.path.abspath(
                os.path.join(_PROJECT_ROOT, p.lstrip("./\\"))
            )
        self.chroma_db_path = abs_path(self.chroma_db_path)
        self.data_folder = abs_path(self.data_folder)
        # Make database URL absolute with forward slashes (required for SQLite on Windows)
        if self.database_url.startswith("sqlite:///"):
            raw = self.database_url.replace("sqlite:///", "")
            self.database_url = "sqlite:///" + abs_path(raw).replace("\\", "/")
        return self


settings = Settings()
