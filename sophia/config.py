from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM
    anthropic_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    llm_provider: str = "anthropic"  # "anthropic" or "ollama"
    llm_model: str = "claude-sonnet-4-6"

    # Database
    database_url: str = "sqlite+aiosqlite:///sophia.db"

    # Logging
    log_level: str = "INFO"

    # Hats
    default_hat: str = "customer-service"
    hats_dir: str = "./hats"

    # Consequence Tree (Phase 2+)
    tree_max_depth: int = 3
    tree_prune_threshold: float = 0.05

    # Catastrophic threshold (core safety, not hat-configurable)
    catastrophic_threshold: float = -0.8

    # Memory (Phase 6)
    memory_provider: str = "mock"  # "surrealdb" or "mock"
    surrealdb_url: str = "ws://localhost:8529"
    surrealdb_user: str = "root"
    surrealdb_pass: str = "root"
    surrealdb_namespace: str = "sophia"
    surrealdb_database: str = "memory"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
