import io
import logging
import tempfile
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


class WhisperLocalSTT:
    """
    Local STT via faster-whisper (CPU or GPU). Model loads lazily on first
    transcribe() so import doesn't block startup.

    Config:
      provider: whisper_local
      model: small     # tiny | base | small | medium | large-v3
      device: auto     # auto | cpu | cuda | mps
      compute_type: default  # default | int8 | float16 | int8_float16
      beam_size: 1
    """

    def __init__(self, cfg: dict):
        self.model_name = cfg.get("model", "small")
        self.device = cfg.get("device", "auto")
        self.compute_type = cfg.get("compute_type", "default")
        self.beam_size = int(cfg.get("beam_size", 1))
        self._model = None
        self._lock = threading.Lock()

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            from faster_whisper import WhisperModel
            logger.info("Loading faster-whisper model=%s device=%s",
                        self.model_name, self.device)
            kwargs = {"device": self.device}
            if self.compute_type != "default":
                kwargs["compute_type"] = self.compute_type
            self._model = WhisperModel(self.model_name, **kwargs)
            logger.info("faster-whisper loaded")
            return self._model

    def transcribe(self, audio_bytes: bytes, filename: str = "audio.webm",
                   language: str | None = None) -> str:
        model = self._ensure_model()
        suffix = Path(filename).suffix or ".webm"
        # faster-whisper needs a path (it uses ffmpeg/av under the hood)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as f:
            f.write(audio_bytes)
            f.flush()
            segments, info = model.transcribe(
                f.name,
                language=language,
                beam_size=self.beam_size,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
            )
            parts = [s.text.strip() for s in segments if s.text and s.text.strip()]
        return " ".join(parts).strip()
