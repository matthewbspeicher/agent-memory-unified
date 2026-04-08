import sys
from pathlib import Path

# Ensure project root is in sys.path for shared module imports
# This enables: from shared.auth.validate import ...
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import uvicorn
from config import load_config
from api.app import create_app


def _build_app():
    config = load_config()
    return create_app(
        broker=None,  # Lifespan handles all broker creation
        enable_agent_framework=True,
        config=config,
    )


app = _build_app()


if __name__ == "__main__":
    config = load_config()
    uvicorn.run(app, host=config.api_host, port=config.api_port)
