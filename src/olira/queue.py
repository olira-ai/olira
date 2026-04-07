"""Background worker and bounded queue for log batching and flush."""

import atexit
import logging
import queue
import threading
import time
from collections.abc import Callable
from typing import Any

from .models import LogWire

logger = logging.getLogger("olira")

# Key redaction for logs
REDACTED = "olira_***"


class BackgroundWorker:
    """
    Daemon thread that drains a bounded queue, batches log entries, and sends via send_batch.
    flush() blocks until the queue is empty and in-flight batch is done.
    """

    def __init__(
        self,
        *,
        send_batch: Callable[[list[dict[str, Any]]], None],
        batch_size: int = 50,
        flush_interval: float = 1.5,
        max_queue_size: int = 10_000,
        on_error: str | Callable[[Exception, list[str]], None] = "drop",
    ) -> None:
        self._send_batch = send_batch
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._max_queue_size = max_queue_size
        self._on_error = on_error
        self._q: queue.Queue[LogWire | None] = queue.Queue(maxsize=max_queue_size)
        self._lock = threading.Lock()
        self._pending: list[LogWire] = []
        self._shutdown = threading.Event()
        self._thread: threading.Thread | None = None
        self._closed = False

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        atexit.register(self._atexit_flush)

    def _atexit_flush(self) -> None:
        if not self._closed:
            self.flush()

    def enqueue(self, event: LogWire) -> bool:
        """Enqueue one log entry. Returns False if queue full (entry dropped)."""
        try:
            self._q.put(event, block=False)
            return True
        except queue.Full:
            self._notify_error(
                Exception("Event queue full; event dropped"),
                [event.event_name],
            )
            return False

    def _notify_error(self, error: Exception, event_names: list[str]) -> None:
        if self._on_error == "drop":
            logger.debug(
                "Events dropped: %s (names only)",
                event_names[:5],
                exc_info=error,
            )
        elif self._on_error == "raise":
            raise error
        elif callable(self._on_error):
            self._on_error(error, event_names)

    def _run(self) -> None:
        last_flush = time.monotonic()
        while not self._shutdown.is_set():
            try:
                timeout = max(0.1, self._flush_interval - (time.monotonic() - last_flush))
                item = self._q.get(timeout=timeout)
            except queue.Empty:
                item = None
            if item is None:
                # Flush interval elapsed or shutdown
                pass
            else:
                with self._lock:
                    self._pending.append(item)
                if len(self._pending) >= self._batch_size:
                    self._flush_pending()
                    last_flush = time.monotonic()
                continue
            with self._lock:
                if self._pending:
                    self._flush_pending()
            last_flush = time.monotonic()
        with self._lock:
            if self._pending:
                self._flush_pending()

    def _flush_pending(self) -> None:
        if not self._pending:
            return
        batch = self._pending[:]
        self._pending.clear()
        try:
            payloads = [e.model_dump(mode="json") for e in batch]
            self._send_batch(payloads)
        except Exception as e:
            self._notify_error(e, [e.event_name for e in batch])

    def flush(self) -> None:
        """Block until queue is empty and current batch is sent."""
        if self._thread is None:
            return
        # Drain queue into pending
        while True:
            try:
                item = self._q.get_nowait()
                if item is None:
                    break
                with self._lock:
                    self._pending.append(item)
            except queue.Empty:
                break
        with self._lock:
            if self._pending:
                self._flush_pending()

    def close(self) -> None:
        self._closed = True
        atexit.unregister(self._atexit_flush)
        self._shutdown.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        with self._lock:
            if self._pending:
                self._flush_pending()
