"""Tests for ml_layer.worker.MlWorker."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from zt_shared.models.events import EmailContext, FileRequestedEvent

from ml_layer.worker import ML_SLA_MS, MlWorker


def _make_event(s3_url: str = "s3://bucket/key") -> FileRequestedEvent:
    return FileRequestedEvent(
        job_id=uuid4(),
        s3_url=s3_url,
        sha256="a" * 64,
        email_context=EmailContext(
            sender="user@example.com",
            subject="hi",
            body_text="body",
        ),
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture()
def worker() -> MlWorker:
    """MlWorker with model existence, analyzer and Kafka clients mocked out."""
    with (
        patch("ml_layer.worker.os.path.exists", return_value=True),
        patch("ml_layer.worker.StaticAnalyzer"),
        patch("ml_layer.worker.KafkaPublisher"),
        patch("ml_layer.worker.KafkaSubscriber"),
    ):
        w = MlWorker()
    w.publisher = AsyncMock()
    w.subscriber = AsyncMock()
    w.analyzer = MagicMock()
    w.analyzer.analyze = AsyncMock(return_value=(50, ["high_risk"]))
    return w


def test_init_raises_when_model_missing() -> None:
    with (
        patch("ml_layer.worker.os.path.exists", return_value=False),
        patch("ml_layer.worker.KafkaPublisher"),
        patch("ml_layer.worker.KafkaSubscriber"),
    ):
        with pytest.raises(FileNotFoundError):
            MlWorker()


async def test_start_and_stop(worker: MlWorker) -> None:
    await worker.start()
    worker.publisher.start.assert_awaited_once()
    worker.subscriber.start.assert_awaited_once()

    await worker.stop()
    worker.subscriber.stop.assert_awaited_once()
    worker.publisher.stop.assert_awaited_once()


def test_get_s3_client_is_lazy_and_reused(worker: MlWorker) -> None:
    with patch("ml_layer.worker.boto3.client", return_value=MagicMock()) as mock_client:
        first = worker._get_s3_client()
        second = worker._get_s3_client()
    assert first is second
    mock_client.assert_called_once()


async def test_download_file_http(worker: MlWorker) -> None:
    resp = MagicMock(content=b"http-bytes")
    resp.raise_for_status = MagicMock()
    client = AsyncMock()
    client.get.return_value = resp

    with patch("ml_layer.worker.httpx.AsyncClient") as cls:
        cls.return_value.__aenter__.return_value = client
        data = await worker._download_file("https://host/file.pdf")

    assert data == b"http-bytes"
    resp.raise_for_status.assert_called_once()


async def test_download_file_s3(worker: MlWorker) -> None:
    s3 = MagicMock()
    s3.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=b"s3-bytes"))}
    worker._s3_client = s3

    data = await worker._download_file("s3://bucket/path/to.pdf")

    assert data == b"s3-bytes"
    s3.get_object.assert_called_once_with(Bucket="bucket", Key="path/to.pdf")


async def test_download_file_unsupported_scheme(worker: MlWorker) -> None:
    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        await worker._download_file("ftp://host/file.pdf")


async def test_handle_event_success(worker: MlWorker) -> None:
    worker._download_file = AsyncMock(return_value=b"%PDF-1.7")  # type: ignore[method-assign]
    event = _make_event()

    await worker.handle_event(event)

    worker.publisher.publish.assert_awaited_once()
    topic, result = worker.publisher.publish.await_args.args
    assert topic == worker.config.kafka.topic_out
    assert result.job_id == event.job_id
    assert result.risk_score == 50
    assert result.static_tags == ["high_risk"]


async def test_handle_event_publishes_error_result_on_failure(worker: MlWorker) -> None:
    worker._download_file = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
    event = _make_event()

    await worker.handle_event(event)

    worker.publisher.publish.assert_awaited_once()
    _, result = worker.publisher.publish.await_args.args
    assert result.risk_score == 0
    assert result.static_tags == ["analysis_error"]


async def test_handle_event_swallows_error_publish_failure(worker: MlWorker) -> None:
    worker._download_file = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
    worker.publisher.publish = AsyncMock(side_effect=RuntimeError("kafka down"))
    event = _make_event()

    # Must not raise even though the fallback publish also fails.
    await worker.handle_event(event)


async def test_publish_result_warns_on_sla_breach(
    worker: MlWorker, caplog: pytest.LogCaptureFixture
) -> None:
    breached_start = time.perf_counter() - (ML_SLA_MS + 500) / 1000
    with caplog.at_level("WARNING"):
        await worker._publish_result(uuid4(), 10, ["t"], breached_start)
    assert any("SLA breach" in r.message for r in caplog.records)


async def test_publish_result_no_warn_within_sla(
    worker: MlWorker, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("WARNING"):
        await worker._publish_result(uuid4(), 10, ["t"], time.perf_counter())
    assert not any("SLA breach" in r.message for r in caplog.records)
