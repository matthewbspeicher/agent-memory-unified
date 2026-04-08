"""Development server entrypoint with logging overrides."""

import logging

logging.basicConfig(level=logging.INFO)
logging.getLogger("integrations.bittensor").setLevel(logging.DEBUG)
logging.getLogger("btdecode").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.WARNING)

import uvicorn

from main import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
