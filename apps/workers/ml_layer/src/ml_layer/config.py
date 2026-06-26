from functools import cache

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class KafkaSettings(BaseModel):
    bootstrap_servers: str = "localhost:9092"
    topic_in: str = "file.requested"
    topic_out: str = "ml_layer.result"
    group_id: str = "ml-layer-worker"


class Settings(BaseSettings):
    # Nested env vars use a double-underscore delimiter, e.g.
    # KAFKA__BOOTSTRAP_SERVERS=broker:9092 overrides kafka.bootstrap_servers.
    model_config = SettingsConfigDict(env_nested_delimiter="__")

    kafka: KafkaSettings = KafkaSettings()

    minio_endpoint: str = "http://localhost:9000"
    aws_access_key: str = "minioadmin"
    aws_secret_key: str = "minioadmin"

    model_path: str = "models/ml_model_pdf.onnx"


@cache
def get_config() -> Settings:
    settings = Settings()
    return settings
