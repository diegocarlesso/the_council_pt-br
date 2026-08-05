"""
translator/worker.py

Thread de trabalho: retira um lote da fila, consulta o LLM, valida a
resposta, grava no SQLite e segue para o próximo lote - nunca bloqueia o
programa principal (a fila é quem absorve a espera pela resposta do
modelo, ver queue.py).

Política de retentativa por item (ver validator.py e config.PipelineConfig
.item_retry_limit): a cada tentativa, só os itens que falharam validação
na tentativa anterior são reenviados (lote cada vez menor) - itens que já
passaram são gravados imediatamente e nunca reenviados. Depois de esgotar
as tentativas, o que ainda falha é gravado como status="needs_review" (com
a última tradução obtida, mesmo que inválida, ou vazio se o próprio LLM
nunca respondeu) - nunca é descartado silenciosamente.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Callable, Optional

from .database import TranslationEntry, TranslationMemoryDB
from .llm import LLMBackend, LLMError
from .logger import get_logger
from .metrics import Metrics
from .prompt import PromptBuilder
from .queue import Batch, TranslationQueue, WorkItem
from .utils import extract_json_object
from .validator import BatchValidator, ItemValidationResult

log = get_logger("worker")


class TranslationWorker(threading.Thread):
    def __init__(
        self,
        worker_id: int,
        work_queue: TranslationQueue,
        db: TranslationMemoryDB,
        llm: LLMBackend,
        prompt_builder: PromptBuilder,
        validator: BatchValidator,
        metrics: Metrics,
        item_retry_limit: int,
        stop_event: Optional[threading.Event] = None,
        on_batch_done: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(name=f"Worker-{worker_id}", daemon=True)
        self._queue = work_queue
        self._db = db
        self._llm = llm
        self._prompt_builder = prompt_builder
        self._validator = validator
        self._metrics = metrics
        self._item_retry_limit = item_retry_limit
        self._stop_event = stop_event
        self._on_batch_done = on_batch_done

    def run(self) -> None:
        log.info("iniciado")
        try:
            while True:
                batch = self._queue.get()
                if batch is None:
                    break
                try:
                    if self._stop_event is not None and self._stop_event.is_set():
                        log.info(
                            "parada solicitada - descartando lote %d (categoria=%s, %d itens) sem processar; "
                            "será retomado na próxima execução (nada foi gravado para ele)",
                            batch.batch_id, batch.category, len(batch.items),
                        )
                        continue
                    self._process_batch(batch)
                except Exception:
                    # Nunca deixa um bug inesperado matar a thread no meio de
                    # uma execução de dias - o lote fica sem linha no banco
                    # (continua "pendente" do ponto de vista do pipeline) e
                    # será reprocessado numa próxima execução, sem corrupção.
                    log.exception(
                        "erro inesperado processando lote %d (categoria=%s, %d itens) - "
                        "lote não gravado, será reprocessado numa próxima execução",
                        batch.batch_id, batch.category, len(batch.items),
                    )
                    self._metrics.record_batch(errors=len(batch.items))
                finally:
                    self._queue.task_done()
                    if self._on_batch_done is not None:
                        self._on_batch_done()
        finally:
            self._db.close_current_thread_connection()
            log.info("finalizado")

    # ------------------------------------------------------------------

    def _process_batch(self, batch: Batch) -> None:
        pending_items: list[WorkItem] = list(batch.items)
        menu_boot_ids = {it.canonical_id for it in batch.items if it.menu_boot_suspect}
        source_by_id = {it.canonical_id: it.text for it in batch.items}
        usage_by_id = {it.canonical_id: it.usage_count for it in batch.items}

        total_prompt_tokens = 0
        total_completion_tokens = 0
        max_attempts = self._item_retry_limit + 1

        for attempt in range(1, max_attempts + 1):
            if not pending_items:
                break
            is_last_attempt = attempt == max_attempts
            pairs = [(it.canonical_id, it.text) for it in pending_items]
            texts = [text for _cid, text in pairs]

            log.info(
                "lote %d (%s) tentativa %d/%d: enviando %d item(ns) ao modelo, aguardando resposta...",
                batch.batch_id, batch.category, attempt, max_attempts, len(pending_items),
            )
            call_start = time.monotonic()
            try:
                llm_result = self._llm.translate(
                    self._prompt_builder.system_prompt(texts),
                    self._prompt_builder.user_message(batch.category, pairs),
                    item_count=len(pending_items),
                )
                log.info(
                    "lote %d (%s) tentativa %d/%d: resposta recebida em %.1fs",
                    batch.batch_id, batch.category, attempt, max_attempts, time.monotonic() - call_start,
                )
                if llm_result.usage:
                    total_prompt_tokens += llm_result.usage.get("prompt_tokens", 0) or 0
                    total_completion_tokens += llm_result.usage.get("completion_tokens", 0) or 0
                response = extract_json_object(llm_result.content)
            except (LLMError, json.JSONDecodeError) as e:
                log.warning(
                    "lote %d (%s) tentativa %d/%d falhou: %s",
                    batch.batch_id, batch.category, attempt, max_attempts, e,
                )
                if is_last_attempt:
                    self._flush_failed_call(pending_items, batch.category, str(e))
                    pending_items = []
                else:
                    self._metrics.record_batch(retries=len(pending_items))
                continue

            response = {
                key: (value if isinstance(value, str) else str(value))
                for key, value in response.items()
                if isinstance(key, str)
            }
            valid, invalid = self._validator.validate_batch(pairs, response, menu_boot_ids)

            if valid:
                self._flush_valid(valid, source_by_id, usage_by_id, batch.category)

            if not invalid:
                pending_items = []
                break

            if is_last_attempt:
                self._flush_needs_review(invalid, source_by_id, usage_by_id, batch.category)
                pending_items = []
            else:
                log.info(
                    "lote %d (%s): %d item(ns) reprovado(s) na tentativa %d/%d, reenviando isoladamente (%s)",
                    batch.batch_id, batch.category, len(invalid), attempt, max_attempts,
                    invalid[0].errors[0] if invalid[0].errors else "motivo desconhecido",
                )
                self._metrics.record_batch(retries=len(invalid))
                invalid_ids = {r.canonical_id for r in invalid}
                pending_items = [it for it in pending_items if it.canonical_id in invalid_ids]

        self._metrics.record_batch(prompt_tokens=total_prompt_tokens, completion_tokens=total_completion_tokens)

    # ------------------------------------------------------------------

    def _flush_valid(
        self,
        results: list[ItemValidationResult],
        source_by_id: dict[str, str],
        usage_by_id: dict[str, int],
        category: str,
    ) -> None:
        entries = [
            TranslationEntry(
                canonical_id=r.canonical_id,
                source=source_by_id[r.canonical_id],
                target=r.target or "",
                category=category,
                status="draft",
                usage_count=usage_by_id.get(r.canonical_id, 0),
                context=category,
            )
            for r in results
        ]
        self._db.upsert_many(entries)
        self._metrics.record_batch(valid=len(entries))
        for r in results:
            if r.warnings:
                log.debug("%s: %s", r.canonical_id, "; ".join(r.warnings))

    def _flush_needs_review(
        self,
        results: list[ItemValidationResult],
        source_by_id: dict[str, str],
        usage_by_id: dict[str, int],
        category: str,
    ) -> None:
        entries = [
            TranslationEntry(
                canonical_id=r.canonical_id,
                source=source_by_id[r.canonical_id],
                target=r.target or "",
                category=category,
                status="needs_review",
                usage_count=usage_by_id.get(r.canonical_id, 0),
                context=category,
            )
            for r in results
        ]
        self._db.upsert_many(entries)
        self._metrics.record_batch(needs_review=len(entries))
        for r in results:
            log.warning("needs_review '%s': %s", r.canonical_id, "; ".join(r.errors) or "sem detalhes")

    def _flush_failed_call(self, items: list[WorkItem], category: str, reason: str) -> None:
        """Usado quando a própria chamada ao LLM/parse da resposta falhou
        (sem tradução nenhuma para validar) após esgotar as retentativas."""
        entries = [
            TranslationEntry(
                canonical_id=it.canonical_id,
                source=it.text,
                target="",
                category=category,
                status="needs_review",
                usage_count=it.usage_count,
                context=category,
            )
            for it in items
        ]
        self._db.upsert_many(entries)
        self._metrics.record_batch(needs_review=len(entries), errors=len(entries))
        log.error(
            "%d item(ns) marcados needs_review (categoria=%s) após esgotar retentativas: %s",
            len(entries), category, reason,
        )
