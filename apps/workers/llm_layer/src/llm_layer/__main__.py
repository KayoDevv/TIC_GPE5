"""``python -m llm_layer`` entrypoint."""

import asyncio

from llm_layer.worker import main

if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
