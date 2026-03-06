from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM
    anthropic_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    llm_provider: str = "anthropic"  # "anthropic" or "ollama"
    llm_model: str = "claude-sonnet-4-6"

    # Per-stage model overrides (ADR-032) — all optional, fall back to llm_model
    llm_model_input_gate: str | None = None
    llm_model_proposer: str | None = None
    llm_model_consequence: str | None = None
    llm_model_evaluators: str | None = None
    llm_model_response_gen: str | None = None
    llm_model_memory: str | None = None

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

    # Consequence tree caching (ADR-033)
    consequence_cache_ttl_seconds: int = 3600

    # Catastrophic threshold (core safety, not hat-configurable)
    catastrophic_threshold: float = -0.8

    # Auth
    auth_enabled: bool = False
    auth_bootstrap_key: str = ""

    # Notifications
    notification_provider: str = "log"  # "log" or "webhook"

    # Memory (Phase 6)
    memory_provider: str = "mock"  # "surrealdb" or "mock"
    surrealdb_url: str = "ws://localhost:8529"
    surrealdb_user: str = "root"
    surrealdb_pass: str = "root"
    surrealdb_namespace: str = "sophia"
    surrealdb_database: str = "memory"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
