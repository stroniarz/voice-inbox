import base64
import logging
import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AskBody(BaseModel):
    q: str
    project: str | None = None


class ChannelRegisterBody(BaseModel):
    project: str
    cwd: str | None = None


class ChannelPushBody(BaseModel):
    project: str
    text: str
    meta: dict[str, str] | None = None


class ChannelReplyBody(BaseModel):
    project: str
    text: str


class PermissionRequestBody(BaseModel):
    project: str
    request_id: str
    tool_name: str
    description: str
    input_preview: str = ""


class PermissionRespondBody(BaseModel):
    project: str
    behavior: str  # "allow" | "deny"
    request_id: str | None = None


def make_app(cc_handler=None, ask_handler=None, store=None,
             stt_client=None, tts_client=None,
             public_dir: Path | None = None,
             stt_language: str = "pl",
             channels_bridge=None,
             tts_worker=None,
             archive_replies: bool = True,
             permissions_broker=None,
             archive_permissions: bool = True,
             permissions_language: str = "pl") -> FastAPI:
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

    @app.post("/channels/register")
    async def channels_register(body: ChannelRegisterBody):
        if channels_bridge is None:
            return JSONResponse({"ok": False, "error": "channels disabled"}, status_code=503)
        await channels_bridge.register(body.project, cwd=body.cwd)
        return {"ok": True}

    @app.post("/channels/push")
    async def channels_push(body: ChannelPushBody):
        if channels_bridge is None:
            return JSONResponse({"ok": False, "error": "channels disabled"}, status_code=503)
        ok = await channels_bridge.push(body.project, body.text, meta=body.meta)
        return {"ok": ok}

    @app.get("/channels/pull")
    async def channels_pull(project: str, timeout: float = 30.0):
        if channels_bridge is None:
            return JSONResponse({"ok": False, "error": "channels disabled"}, status_code=503)
        timeout = max(0.1, min(timeout, 60.0))
        msg = await channels_bridge.pull(project, timeout=timeout)
        if msg is None:
            return Response(status_code=204)  # 204 must have no body per HTTP spec
        return {"ok": True, "message": msg}

    @app.get("/channels/active")
    def channels_active():
        if channels_bridge is None:
            return JSONResponse({"ok": False, "error": "channels disabled"}, status_code=503)
        return {"ok": True, "projects": channels_bridge.active_projects()}

    @app.post("/channels/reply")
    async def channels_reply(body: ChannelReplyBody):
        """CC's `speak` tool hits this endpoint. Enqueue TTS and optionally archive."""
        text = body.text.strip()
        if not text:
            return JSONResponse({"ok": False, "error": "empty text"}, status_code=400)
        spoken = False
        if tts_worker is not None:
            try:
                tts_worker.enqueue(text, tag="default")
                spoken = True
            except Exception as e:
                logger.exception("TTS enqueue failed: %s", e)
        archived = False
        if archive_replies and store is not None:
            try:
                from datetime import datetime, timezone
                store.archive_event(
                    source="cc-reply",
                    external_id=f"cc-reply:{body.project}:{datetime.now(timezone.utc).timestamp()}",
                    author=body.project,
                    short=text[:60],
                    title="",
                    body=text,
                    project=body.project,
                )
                archived = True
            except Exception as e:
                logger.exception("archive_event failed: %s", e)
        return {"ok": True, "spoken": spoken, "archived": archived}

    @app.post("/channels/permissions/request")
    async def permissions_request(body: PermissionRequestBody):
        if permissions_broker is None:
            return JSONResponse({"ok": False, "error": "permissions disabled"}, status_code=503)
        await permissions_broker.store_request(
            project=body.project,
            request_id=body.request_id,
            tool_name=body.tool_name,
            description=body.description,
            input_preview=body.input_preview,
        )
        if tts_worker is not None:
            from .channels_permissions import announce_template
            announce = announce_template(
                project=body.project, tool_name=body.tool_name,
                description=body.description, language=permissions_language,
            )
            try:
                tts_worker.enqueue(announce, tag="critical")
            except Exception as e:
                logger.exception("permissions TTS enqueue failed: %s", e)
        if archive_permissions and store is not None:
            try:
                store.archive_event(
                    source="cc-permission-request",
                    external_id=f"perm-req:{body.project}:{body.request_id}",
                    author=body.project,
                    short=f"{body.tool_name}: {body.description[:40]}",
                    title=body.tool_name,
                    body=body.description + ("\n" + body.input_preview if body.input_preview else ""),
                    project=body.project,
                )
            except Exception as e:
                logger.exception("permissions archive failed: %s", e)
        return {"ok": True}

    @app.get("/channels/permissions/pending")
    def permissions_pending(project: str | None = None):
        if permissions_broker is None:
            return JSONResponse({"ok": False, "error": "permissions disabled"}, status_code=503)
        return {"ok": True, "pending": permissions_broker.list_pending(project=project)}

    @app.post("/channels/permissions/respond")
    async def permissions_respond(body: PermissionRespondBody):
        if permissions_broker is None:
            return JSONResponse({"ok": False, "error": "permissions disabled"}, status_code=503)
        if body.behavior not in ("allow", "deny"):
            return JSONResponse({"ok": False, "error": "behavior must be allow|deny"}, status_code=400)
        resolved = await permissions_broker.respond(
            project=body.project, behavior=body.behavior, request_id=body.request_id,
        )
        if resolved is None:
            return JSONResponse({"ok": False, "error": "no matching pending request"}, status_code=404)
        if archive_permissions and store is not None:
            try:
                latency = round(resolved["resolved_ts"] - resolved["created_ts"], 2)
                store.archive_event(
                    source="cc-permission-response",
                    external_id=f"perm-res:{resolved['project']}:{resolved['request_id']}",
                    author=resolved["project"],
                    short=f"{body.behavior} {resolved['tool_name']} ({latency}s)",
                    title=body.behavior,
                    body=f"tool={resolved['tool_name']} latency={latency}s",
                    project=resolved["project"],
                )
            except Exception as e:
                logger.exception("permissions response archive failed: %s", e)
        return {"ok": True, "resolved": resolved}

    @app.get("/channels/permissions/poll")
    async def permissions_poll(project: str, timeout: float = 30.0):
        if permissions_broker is None:
            return JSONResponse({"ok": False, "error": "permissions disabled"}, status_code=503)
        timeout = max(0.1, min(timeout, 60.0))
        verdict = await permissions_broker.pull_verdict(project, timeout=timeout)
        if verdict is None:
            return Response(status_code=204)
        return {"ok": True, "verdict": verdict}

    @app.get("/channels/permissions/log")
    def permissions_log(limit: int = 100):
        if permissions_broker is None:
            return JSONResponse({"ok": False, "error": "permissions disabled"}, status_code=503)
        limit = max(1, min(limit, 500))
        return {"ok": True, "history": permissions_broker.history(limit=limit)}

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
