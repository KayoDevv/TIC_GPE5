from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Configuration centralisée du Core Backend.
    Toutes les valeurs sont lues depuis les variables d'environnement
    ou depuis un fichier .env (pydantic-settings le gère nativement).
    """

    # --- Kafka ---
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_client_id: str = "core-backend"
    kafka_topic_file_requested: str = "file.requested"
    kafka_topic_verdict_result: str = "verdict.result"
    kafka_consumer_group_id: str = "core-backend-verdict"

    # --- S3 / MinIO ---
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket_name: str = "zero-trust-files"
    s3_region: str = "eu-west-3"

    # --- JWT / Auth ---
    jwt_jwks_url: str = "http://localhost:8080/.well-known/jwks.json"
    jwt_audience: str = "zero-trust-api"
    jwt_algorithm: str = "RS256"

    # --- Dev auth bypass (LOCAL ONLY) ---
    # When AUTH_DEV_MODE=true, JWT signature verification is skipped and a fixed
    # dev identity is returned. This exists so the pipeline is testable locally
    # before the SSO/JWKS integration lands. NEVER enable in production.
    auth_dev_mode: bool = False
    auth_dev_sub: str = "dev-user"
    auth_dev_tenant_id: str = "dev-tenant"

    # --- Upload ---
    max_file_size_bytes: int = 35 * 1024 * 1024  # 35 MB

    # --- WebSocket ---
    ws_verdict_timeout_seconds: int = 130
    # How long a submitted job stays claimable by its tenant on the WebSocket.
    job_owner_ttl_seconds: int = 900

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}
