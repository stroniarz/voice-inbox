import logging
import queue
import threading

from .base import TTSClient

log = logging.getLogger(__name__)


class TTSWorker:
    """Single-queue worker that routes each message to one of several TTS clients
    by tag (e.g. 'default', 'critical'). Ensures voices never overlap."""

    def __init__(self, clients: dict[str, TTSClient], default_tag: str = "default"):
        if default_tag not in clients:
            raise ValueError(f"TTSWorker requires '{default_tag}' client")
        self.clients = clients
        self.default_tag = default_tag
        self._queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def enqueue(self, text: str, tag: str = "default") -> None:
        self._queue.put((text, tag))

    def _run(self) -> None:
        while True:
            text, tag = self._queue.get()
            client = self.clients.get(tag) or self.clients[self.default_tag]
            try:
                client.speak(text)
            except Exception as e:
                log.error("TTS speak failed (tag=%s): %s", tag, e)
            finally:
                self._queue.task_done()
