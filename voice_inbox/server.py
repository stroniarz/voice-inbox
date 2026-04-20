import base64
import logging
import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AskBody(BaseModel):
    q: str
    project: str | None = None


def make_app(cc_handler=None, ask_handler=None, store=None,
             stt_client=None, tts_client=None,
             public_dir: Path | None = None,
             stt_language: str = "pl") -> FastAPI:
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
            return JSONResponse({"ok": False, "error": "ask disabled"}, status_code=503)
        answer = ask_handler.ask(body.q, project=body.project)
        return {"ok": True, "answer": answer, "question": body.q, "project": body.project}

    @app.post("/voice")
    async def voice(audio: UploadFile = File(...),
                    project: str | None = Form(default=None)):
        if stt_client is None or ask_handler is None:
            return JSONResponse({"ok": False, "error": "voice disabled"}, status_code=503)
        raw = await audio.read()
        if not raw:
            return JSONResponse({"ok": False, "error": "empty audio"}, status_code=400)
        try:
            transcript = stt_client.transcribe(
                raw, filename=audio.filename or "audio.webm",
                language=stt_language,
            )
        except Exception as e:
            logger.exception("STT failed: %s", e)
            return JSONResponse({"ok": False, "error": f"stt: {e}"}, status_code=500)

        if not transcript.strip():
            return {"ok": True, "transcript": "", "answer": "", "audio_b64": None,
                    "mime": None, "error": "empty transcript"}

        answer = ask_handler.ask(transcript, project=project)

        audio_b64 = None
        mime = None
        if tts_client is not None:
            try:
                audio_bytes, mime = tts_client.synthesize(answer)
                audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
            except Exception as e:
                logger.exception("TTS synthesize failed: %s", e)

        return {
            "ok": True,
            "transcript": transcript,
            "answer": answer,
            "project": project,
            "audio_b64": audio_b64,
            "mime": mime,
        }

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

    # Static PWA — mount last so API routes take priority
    if public_dir is not None and Path(public_dir).is_dir():
        app.mount("/", StaticFiles(directory=str(public_dir), html=True), name="public")

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
