import json
import logging
from typing import Optional, TypeVar

from aiokafka import AIOKafkaProducer
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

class KafkaPublisher:
    """
    A generic async wrapper for AIOKafkaProducer.
    Takes a Pydantic model, serializes it to JSON, and publishes it securely.
    """

    def __init__(self, bootstrap_servers: str, client_id: Optional[str] = None):
        self.producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            client_id=client_id,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        self._started = False

    async def start(self) -> None:
        """Connects to the Kafka broker."""
        if not self._started:
            await self.producer.start()
            self._started = True
            logger.info("Producer started.")

    async def stop(self) -> None:
        """Disconnects from the Kafka broker."""
        if self._started:
            await self.producer.stop()
            self._started = False
            logger.info("Producer stopped.")

    async def publish(self, topic: str, event: BaseModel) -> None:
        """Validates internally (via standard BaseModel) and sends the event to the topic."""
        if not self._started:
            raise RuntimeError("KafkaPublisher must be started before publishing.")
        
        # Pydantic internally dumps to dict compatible with json
        # By using model_dump(mode='json'), datetimes/UUIDs are correctly stringified
        payload = event.model_dump(mode='json')
        
        try:
            await self.producer.send_and_wait(topic, value=payload)
            logger.debug(f"Event published to {topic}: {payload}")
        except Exception as e:
            logger.error(f"Failed to publish to {topic}: {e}")
            raise e
