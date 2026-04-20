import logging
import threading

import uvicorn
from fastapi import FastAPI, Request

logger = logging.getLogger(__name__)


def make_app(cc_handler) -> FastAPI:
    app = FastAPI(title="voice-inbox")

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/cc-event")
    async def cc_event(req: Request):
        try:
            payload = await req.json()
        except Exception:
            payload = {}
        try:
            cc_handler(payload)
        except Exception as e:
            logger.exception("CC handler failed: %s", e)
        return {"ok": True}

    return app


def serve_in_thread(app: FastAPI, host: str, port: int) -> threading.Thread:
    config = uvicorn.Config(
        app, host=host, port=port,
        log_level="warning", access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="voice-inbox-http", daemon=True)
    thread.start()
    return thread
