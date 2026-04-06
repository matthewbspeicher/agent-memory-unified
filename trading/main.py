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
