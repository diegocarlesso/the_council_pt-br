"""
translator/metrics.py

Contadores thread-safe de progresso (traduzidas, pendentes, erros,
retentativas, tokens) e uma thread de relatório que loga um snapshot em
intervalos regulares - é assim que uma execução de dias sem supervisão
fica auditável: basta olhar o log (ou o console) para saber velocidade e
ETA a qualquer momento, sem precisar interromper o processo.

O lock aqui é deliberadamente simples (um threading.Lock por instância,
seção crítica mínima - só incrementa inteiros) porque as atualizações são
por LOTE (uma vez por lote concluído por worker), não por string - com
batch_size=40 e alguns workers, a contenção neste lock é irrelevante
perto do tempo gasto esperando o LLM.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from .logger import get_logger

log = get_logger("metrics")


@dataclass(frozen=True)
class MetricsSnapshot:
    total: int
    translated: int
    needs_review: int
    errors: int
    retries: int
    pending: int
    elapsed_seconds: float
    strings_per_min: float
    tokens_per_min: float
    eta_seconds: float | None


def _format_eta(seconds: float | None) -> str:
    if seconds is None or seconds == float("inf"):
        return "indeterminado"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


class Metrics:
    """Contadores de uma execução do pipeline. `total` é o total de
    strings únicas traduzíveis do corpus (vindo de preprocessed.json),
    incluindo as que já estavam resolvidas em cache antes desta execução
    começar - isso é o que permite calcular pendentes/ETA corretamente
    mesmo ao retomar um processamento interrompido."""

    def __init__(self, total_translatable: int, already_done: int = 0) -> None:
        self.total = total_translatable
        self._lock = threading.Lock()
        self._start = time.monotonic()
        self._already_done = already_done
        self._translated_this_run = 0
        self._needs_review = 0
        self._errors = 0
        self._retries = 0
        self._prompt_tokens = 0
        self._completion_tokens = 0

    def record_batch(
        self,
        *,
        valid: int = 0,
        needs_review: int = 0,
        errors: int = 0,
        retries: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        with self._lock:
            self._translated_this_run += valid
            self._needs_review += needs_review
            self._errors += errors
            self._retries += retries
            self._prompt_tokens += prompt_tokens
            self._completion_tokens += completion_tokens

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            translated_this_run = self._translated_this_run
            needs_review = self._needs_review
            errors = self._errors
            retries = self._retries
            total_tokens = self._prompt_tokens + self._completion_tokens

        elapsed = max(1e-6, time.monotonic() - self._start)
        done_total = self._already_done + translated_this_run + needs_review
        pending = max(0, self.total - done_total)

        strings_per_min = (translated_this_run + needs_review) / elapsed * 60.0
        tokens_per_min = total_tokens / elapsed * 60.0

        eta_seconds: float | None
        if strings_per_min > 0:
            eta_seconds = pending / (strings_per_min / 60.0)
        else:
            eta_seconds = None if pending == 0 else float("inf")

        return MetricsSnapshot(
            total=self.total,
            translated=translated_this_run,
            needs_review=needs_review,
            errors=errors,
            retries=retries,
            pending=pending,
            elapsed_seconds=elapsed,
            strings_per_min=strings_per_min,
            tokens_per_min=tokens_per_min,
            eta_seconds=eta_seconds,
        )


class MetricsReporter(threading.Thread):
    """Thread daemon que loga um snapshot de métricas a cada `interval`
    segundos até stop() ser chamado."""

    def __init__(self, metrics: Metrics, interval_seconds: float) -> None:
        super().__init__(name="MetricsReporter", daemon=True)
        self._metrics = metrics
        self._interval = interval_seconds
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.wait(self._interval):
            self._log_snapshot()
        self._log_snapshot()

    def stop(self) -> None:
        self._stop_event.set()

    def _log_snapshot(self) -> None:
        s = self._metrics.snapshot()
        log.info(
            "total=%d traduzidas=%d p/revisão=%d pendentes=%d | %.1f str/min | %.0f tok/min | "
            "erros=%d retentativas=%d | ETA %s",
            s.total, s.translated, s.needs_review, s.pending,
            s.strings_per_min, s.tokens_per_min,
            s.errors, s.retries, _format_eta(s.eta_seconds),
        )
