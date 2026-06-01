# Shared Python Core (`zt_shared`)

This standalone package contains the foundational libraries shared by all the Python microservices (Workers and API Gateway) of the Zero-Trust project.

## Contents

- `zt_shared/models/`: strict Pydantic V2 data models based on the Kafka JSON Schemas.
- `zt_shared/kafka/`: robust async wrappers (`KafkaSubscriber`, `KafkaPublisher`) built on `aiokafka`.

## Key Commands (Development)

To develop in this shared module locally (without impacting the rest of the system), we use a traditional Python `venv` virtual environment. Here are the essential commands to run from the `packages/core/` directory:

### 1. Initialize the project (first time)
```bash
# Create the virtual environment in the "venv" folder
python3 -m venv venv

# Activate the environment
source venv/bin/activate

# Install the package in development mode with its tools (pytest, etc.)
pip install -e ".[dev]"
```

### 2. Run the test suite
The `command not found: pytest` error occurs if the `venv` is not activated. The package is configured to require 100% code coverage.
```bash
# Always make sure to activate the environment first
source venv/bin/activate

# Run pytest with the coverage report in the terminal
pytest --cov=zt_shared --cov-report=term-missing
```

### 3. Usage in other Workers
In the workers' code (e.g. `apps/workers/ml_layer`), this package is easily imported thanks to its structure:
```python
from zt_shared.models.events import FileRequestedEvent
from zt_shared.kafka import KafkaSubscriber
```
