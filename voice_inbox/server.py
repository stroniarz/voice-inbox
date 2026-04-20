import logging
import threading

import uvicorn
from fastapi import FastAPI, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AskBody(BaseModel):
    q: str
    project: str | None = None


def make_app(cc_handler=None, ask_handler=None, store=None) -> FastAPI:
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
        if cc_handler is None:
            return {"ok": False, "error": "cc disabled"}
        try:
            cc_handler(payload)
        except Exception as e:
            logger.exception("CC handler failed: %s", e)
        return {"ok": True}

    @app.post("/ask")
    async def ask(body: AskBody):
        if ask_handler is None:
            return {"ok": False, "error": "ask disabled"}
        answer = ask_handler.ask(body.q, project=body.project)
        return {"ok": True, "answer": answer, "question": body.q,
                "project": body.project}

    @app.get("/status")
    def status(hours: int = 24):
        if store is None:
            return {"ok": False, "error": "no store"}
        return {
            "ok": True,
            "hours": hours,
            "projects": store.project_summary(hours=hours),
            "events": store.recent_events(hours=hours, limit=50),
        }

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
