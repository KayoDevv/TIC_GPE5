import json
import logging
from typing import Type, TypeVar, Callable, Awaitable, Any, Optional
from aiokafka import AIOKafkaConsumer
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

class KafkaSubscriber:
    """
    A generic async wrapper for AIOKafkaConsumer.
    Consumes a topic, parses the JSON payload into a strict Pydantic model (T),
    and dispatches it to the provided async handler.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        topic: str,
        model: Type[T],
        handler: Callable[[T], Awaitable[None]],
        auto_offset_reset: str = "earliest",
    ):
        self.topic = topic
        self.model = model
        self.handler = handler
        self.consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            auto_offset_reset=auto_offset_reset,
            enable_auto_commit=True,
            value_deserializer=lambda m: m.decode('utf-8')
        )
        self._running = False

    async def start(self):
        """Connects to Kafka and starts polling for messages."""
        logger.info(f"Starting consumer for topic {self.topic}...")
        await self.consumer.start()
        self._running = True
        try:
            async for msg in self.consumer:  # pragma: no branch
                if not self._running:
                    break
                await self._process_message(msg.value)
        finally:
            await self.consumer.stop()
            logger.info(f"Consumer for topic {self.topic} stopped.")

    async def stop(self):
        """Signals the consumer loop to stop."""
        self._running = False

    async def _process_message(self, raw_value: str):
        """Parses the raw JSON string into the Pydantic model and calls the handler."""
        try:
            data = json.loads(raw_value)
            validated_event = self.model.model_validate(data)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON from {self.topic}: {e} (payload: {raw_value})")
            return
        except ValidationError as e:
            logger.error(f"Schema validation failed for {self.topic}: {e.errors()} (payload: {raw_value})")
            return

        try:
            await self.handler(validated_event)
        except Exception as e:
            logger.exception(f"Exception raised in handler for {self.topic}: {e}")
