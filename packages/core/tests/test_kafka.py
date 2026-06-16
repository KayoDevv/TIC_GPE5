import json
from datetime import datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from zt_shared.kafka.consumer import KafkaSubscriber
from zt_shared.kafka.producer import KafkaPublisher
from zt_shared.models.events import LlmLayerResultEvent


@pytest.fixture
def sample_event():
    return LlmLayerResultEvent(
        job_id=uuid4(),
        is_malicious=True,
        explanation_text="Test",
        confidence_score=99,
        timestamp=datetime.now()
    )

@pytest.mark.asyncio
async def test_kafka_publisher_start_stop():
    with patch("zt_shared.kafka.producer.AIOKafkaProducer") as mock_producer_class:
        mock_producer = AsyncMock()
        mock_producer_class.return_value = mock_producer

        publisher = KafkaPublisher(bootstrap_servers="localhost:9092")
        
        # Test start
        await publisher.start()
        mock_producer.start.assert_awaited_once()
        assert publisher._started is True

        # Test stop
        await publisher.stop()
        mock_producer.stop.assert_awaited_once()
        assert publisher._started is False


@pytest.mark.asyncio
async def test_kafka_publisher_publish(sample_event):
    with patch("zt_shared.kafka.producer.AIOKafkaProducer") as mock_producer_class:
        mock_producer = AsyncMock()
        mock_producer_class.return_value = mock_producer

        publisher = KafkaPublisher(bootstrap_servers="localhost:9092")
        await publisher.start()

        await publisher.publish("test_topic", sample_event)
        
        # Verify the message was sent
        mock_producer.send_and_wait.assert_awaited_once()
        args, kwargs = mock_producer.send_and_wait.call_args
        assert args[0] == "test_topic"
        
        # Verify JSON serialization
        payload = kwargs["value"]
        assert "job_id" in payload
        assert payload["is_malicious"] is True


@pytest.mark.asyncio
async def test_kafka_publisher_not_started(sample_event):
    publisher = KafkaPublisher(bootstrap_servers="localhost:9092")
    with pytest.raises(RuntimeError):
        await publisher.publish("test_topic", sample_event)


@pytest.mark.asyncio
async def test_kafka_subscriber_processing():
    """Test that subscriber correctly decodes, validates and dispatches messages."""
    
    handler_mock = AsyncMock()
    
    # Create a subscriber
    subscriber = KafkaSubscriber(
        bootstrap_servers="localhost:9092",
        group_id="test_group",
        topic="test_topic",
        model=LlmLayerResultEvent,
        handler=handler_mock
    )
    
    # Simulate a raw message
    valid_json = {
        "job_id": str(uuid4()),
        "is_malicious": False,
        "explanation_text": "Clean file",
        "timestamp": datetime.now().isoformat()
    }
    
    # Process it directly to avoid needing to mock the entire AIOKafkaConsumer async iterator
    await subscriber._process_message(json.dumps(valid_json))
    
    # Assert handler was called with parsed Pydantic model
    handler_mock.assert_awaited_once()
    event = handler_mock.call_args[0][0]
    assert isinstance(event, LlmLayerResultEvent)
    assert event.is_malicious is False


@pytest.mark.asyncio
async def test_kafka_subscriber_invalid_json():
    handler_mock = AsyncMock()
    subscriber = KafkaSubscriber(
        bootstrap_servers="localhost", group_id="g", topic="t",
        model=LlmLayerResultEvent, handler=handler_mock
    )
    
    # Process bad JSON
    await subscriber._process_message("{bad_json: true")
    # Should catch JSONDecodeError and not call handler
    handler_mock.assert_not_called()


@pytest.mark.asyncio
async def test_kafka_subscriber_validation_error():
    handler_mock = AsyncMock()
    subscriber = KafkaSubscriber(
        bootstrap_servers="localhost", group_id="g", topic="t",
        model=LlmLayerResultEvent, handler=handler_mock
    )
    
    # Missing required fields
    bad_schema_json = {"job_id": str(uuid4())} 
    
    await subscriber._process_message(json.dumps(bad_schema_json))
    # Should catch ValidationError and not call handler
    handler_mock.assert_not_called()

@pytest.mark.asyncio
async def test_kafka_subscriber_start_stop():
    """Test start and stop loop of subscriber."""
    handler_mock = AsyncMock()
    subscriber = KafkaSubscriber(
        bootstrap_servers="localhost", group_id="g", topic="t",
        model=LlmLayerResultEvent, handler=handler_mock
    )
    
    # Mock consumer with a simple async iterator class
    class DummyConsumer:
        def __init__(self):
            self.start = AsyncMock()
            self.stop = AsyncMock()
            self.items = [
                '{"job_id": "00000000-0000-0000-0000-000000000000", "is_malicious": true, "explanation_text": "text", "timestamp": "2024-01-01T00:00:00Z"}',  # noqa: E501
                'bad_json_it_should_stop_before'
            ]
            self.index = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            # On second call, signal stop so it breaks the loop
            if self.index == 1:
                subscriber._running = False
                
            if self.index < len(self.items):
                val = self.items[self.index]
                self.index += 1
                class Msg:
                    value = val
                return Msg()
            raise StopAsyncIteration

    mock_consumer = DummyConsumer()
    subscriber.consumer = mock_consumer
    
    await subscriber.start()
    
    mock_consumer.start.assert_awaited_once()
    mock_consumer.stop.assert_awaited_once()
    # process_message called once
    handler_mock.assert_awaited_once()

@pytest.mark.asyncio
async def test_kafka_subscriber_natural_exhaustion():
    """Test start and stop loop where async iterator is exhausted naturally."""
    handler_mock = AsyncMock()
    subscriber = KafkaSubscriber(
        bootstrap_servers="localhost", group_id="g", topic="t",
        model=LlmLayerResultEvent, handler=handler_mock
    )
    
    class EmptyConsumer:
        def __init__(self):
            self.start = AsyncMock()
            self.stop = AsyncMock()
        def __aiter__(self):
            async def empty_gen():
                class Msg:
                    value = '{"job_id": "00000000-0000-0000-0000-000000000000", "is_malicious": true, "explanation_text": "text", "timestamp": "2024-01-01T00:00:00Z"}'  # noqa: E501
                yield Msg()
            return empty_gen()
            
    subscriber.consumer = EmptyConsumer()
    await subscriber.start()
    assert subscriber._running is True

@pytest.mark.asyncio
async def test_kafka_subscriber_handler_exception():
    """Test when handler raises an exception, it is caught."""
    # handler that raises
    async def bad_handler(event):
        raise ValueError("Something went wrong in handler")
        
    subscriber = KafkaSubscriber(
        bootstrap_servers="localhost", group_id="g", topic="t",
        model=LlmLayerResultEvent, handler=bad_handler
    )
    valid_json = {
        "job_id": str(uuid4()),
        "is_malicious": False,
        "explanation_text": "Test",
        "timestamp": datetime.now().isoformat()
    }
    # Should not raise
    await subscriber._process_message(json.dumps(valid_json))

@pytest.mark.asyncio
async def test_kafka_subscriber_stop_method():
    subscriber = KafkaSubscriber(
        bootstrap_servers="localhost", group_id="g", topic="t",
        model=LlmLayerResultEvent, handler=AsyncMock()
    )
    subscriber._running = True
    await subscriber.stop()
    assert subscriber._running is False

@pytest.mark.asyncio
async def test_kafka_publisher_double_start_stop():
    with patch("zt_shared.kafka.producer.AIOKafkaProducer") as mock_producer_class:
        mock_producer = AsyncMock()
        mock_producer_class.return_value = mock_producer

        publisher = KafkaPublisher(bootstrap_servers="localhost:9092")
        
        await publisher.start()
        await publisher.start() # Should ignore 
        mock_producer.start.assert_awaited_once()
        
        await publisher.stop()
        await publisher.stop() # Should ignore
        mock_producer.stop.assert_awaited_once()

@pytest.mark.asyncio
async def test_kafka_publisher_publish_exception(sample_event):
    with patch("zt_shared.kafka.producer.AIOKafkaProducer") as mock_producer_class:
        mock_producer = AsyncMock()
        mock_producer.send_and_wait.side_effect = Exception("Kafka error")
        mock_producer_class.return_value = mock_producer

        publisher = KafkaPublisher(bootstrap_servers="localhost:9092")
        await publisher.start()

        with pytest.raises(Exception, match="Kafka error"):
            await publisher.publish("test_topic", sample_event)

