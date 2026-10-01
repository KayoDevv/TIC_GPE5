"""Configuration settings for the verdict layer."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_consumer_group_prefix: str = "verdict-layer"
    kafka_topic_ml_result: str = "ml_layer.result"
    kafka_topic_sandbox_result: str = "sandbox_layer.result"
    kafka_topic_llm_result: str = "llm_layer.result"
    kafka_topic_verdict_result: str = "verdict.result"

    redis_url: str = "redis://localhost:6379/0"
    redis_state_ttl_seconds: int = 300
    redis_lock_ttl_seconds: int = 3600

    sandbox_timeout_seconds: int = 125
    reaper_interval_seconds: int = 5

    ml_block_threshold: int = 90
    # Above this score the static model blocks on its own, but only when the
    # behavioral analysis is partial (timeout/error); a clean sandbox still wins.
    ml_solo_block_threshold: int = 98

    default_timeout_verdict: str = "warning"

    ml_abstain_verdict: str = "warning"

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}
