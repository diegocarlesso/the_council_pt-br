"""
translator/translate.py

Ponto de entrada do pipeline de tradução automática (LM Studio local).
Orquestra: preprocessed.json + glossary.json -> memória de tradução
(SQLite, com cache) -> fila -> workers -> LLM -> validação -> SQLite ->
próxima string (ver README do pacote).

Uso (a partir de Data/Packages):
    python -m translator.translate
    python -m translator.translate --workers 4 --batch-size 60
    python -m translator.translate --category Sistema --max-batches 5
    python -m translator.translate --dry-run          # monta lotes e roda a fila sem chamar o LLM
    python -m translator.translate --export-only       # só sincroniza SQLite -> translation_memory.json

Reaproveita preprocessed.json e translation_memory.json tal como
produzidos por preprocess.py/validate_batch.py - não reimplementa
extração nem classificação. Ao final (ou a cada N lotes,
--export-every-n-batches), exporta o banco de volta para
translation_memory.json para manter validate_batch.py e
progress_report.py funcionando sem alteração.
"""
from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
import time
from collections import defaultdict

from .config import TranslatorConfig, load_config
from .database import TranslationMemoryDB
from .llm import LMStudioClient
from .logger import configure_logging, get_logger
from .metrics import Metrics, MetricsReporter
from .prompt import PromptBuilder, load_glossary_terms
from .queue import Batch, TranslationQueue, WorkItem
from .utils import AtomicCounter
from .validator import BatchValidator
from .worker import TranslationWorker

log = get_logger("translate")


def _load_json(path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_worklist(preprocessed: dict, category_filter: str | None) -> list[tuple[str, dict]]:
    """Espelha build_worklist de translate_batch.py: só strings únicas,
    traduzíveis, da categoria pedida (se houver filtro). O corte do que já
    está feito acontece depois, contra o cache do SQLite (build_batches)."""
    canonical = preprocessed["_canonical"]
    worklist = []
    for cid, entry in canonical.items():
        if not entry["translatable"]:
            continue
        if category_filter and entry["primary_category"] != category_filter:
            continue
        worklist.append((cid, entry))
    return worklist


def build_batches(
    worklist: list[tuple[str, dict]],
    already_cached: dict[str, str],
    batch_size: int,
) -> list[Batch]:
    """Agrupa por primary_category (nunca mistura UI com diálogo no mesmo
    lote - mesma regra de translate_batch.py) e quebra em lotes de
    `batch_size`, pulando o que já está resolvido no SQLite."""
    by_category: dict[str, list[WorkItem]] = defaultdict(list)
    for cid, entry in worklist:
        if cid in already_cached:
            continue
        by_category[entry["primary_category"]].append(
            WorkItem(
                canonical_id=cid,
                text=entry["text"],
                usage_count=entry.get("usage_count", 0),
                menu_boot_suspect=bool(entry.get("menu_boot_suspect", False)),
            )
        )

    batches: list[Batch] = []
    batch_id = 0
    for category, items in by_category.items():
        for i in range(0, len(items), batch_size):
            batches.append(Batch(batch_id=batch_id, category=category, items=items[i:i + batch_size]))
            batch_id += 1
    return batches


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--category", default=None, help="Só processa esta categoria primária (ex.: Sistema, Diálogo, Item)")
    parser.add_argument("--batch-size", type=int, default=None, help="Sobrescreve TranslatorConfig.pipeline.batch_size")
    parser.add_argument("--workers", type=int, default=None, help="Sobrescreve TranslatorConfig.pipeline.num_workers")
    parser.add_argument("--max-batches", type=int, default=None, help="Limite de lotes nesta execução (para teste)")
    parser.add_argument("--dry-run", action="store_true", help="Monta lotes e roda a fila/workers sem chamar o LLM de verdade")
    parser.add_argument("--export-only", action="store_true", help="Só exporta o SQLite atual para translation_memory.json e sai")
    parser.add_argument("--stats", action="store_true", help="Só imprime estatísticas do banco e sai")
    parser.add_argument("--quiet", action="store_true", help="Log em nível WARNING no console (arquivo continua em DEBUG)")
    return parser.parse_args(argv)


class _DryRunLLM:
    """Backend fake para --dry-run: não bate na rede, devolve o próprio
    texto original como "tradução" (permite validar toda a canalização de
    fila/workers/validação/SQLite sem depender do LM Studio estar de pé)."""

    def ping(self) -> bool:
        return True

    def translate(self, system_prompt: str, user_content: str, *, item_count: int = 1):
        from .llm import LLMResult

        start = user_content.index("{")
        payload = json.loads(user_content[start:])
        response = {cid: text for cid, text in payload.items()}
        return LLMResult(content=json.dumps(response, ensure_ascii=False), usage=None, model="dry-run")


def run(cfg: TranslatorConfig, args: argparse.Namespace) -> int:
    batch_size = args.batch_size or cfg.pipeline.batch_size
    num_workers = args.workers or cfg.pipeline.num_workers

    if not cfg.paths.preprocessed_json.exists():
        log.error(
            "%s não existe - rode preprocess.py primeiro (etapa 1 do pipeline existente).",
            cfg.paths.preprocessed_json,
        )
        return 1
    if not cfg.paths.glossary_json.exists():
        log.error("%s não existe.", cfg.paths.glossary_json)
        return 1

    db = TranslationMemoryDB(cfg.paths.translation_memory_db)
    db.import_from_json_if_empty(cfg.paths.translation_memory_json)

    if args.export_only:
        db.export_to_json(
            cfg.paths.translation_memory_json,
            source_language=cfg.source_language,
            target_language=cfg.target_language,
        )
        return 0

    if args.stats:
        stats = db.stats()
        log.info(
            "total=%d approved=%d draft=%d needs_review=%d traduzidas=%d por_categoria=%s",
            stats.total, stats.approved, stats.draft, stats.needs_review, stats.translated, stats.by_category,
        )
        return 0

    preprocessed = _load_json(cfg.paths.preprocessed_json)
    glossary_data = _load_json(cfg.paths.glossary_json)
    glossary_terms = load_glossary_terms(glossary_data)

    worklist = build_worklist(preprocessed, args.category)
    all_ids = [cid for cid, _entry in worklist]
    already_cached = db.get_many_cached(all_ids)

    batches = build_batches(worklist, already_cached, batch_size)
    if args.max_batches is not None:
        batches = batches[:args.max_batches]

    pending_strings = sum(len(b) for b in batches)
    log.info(
        "worklist: %d strings traduzíveis únicas, %d já em cache, %d pendentes nesta execução em %d lote(s) (batch_size=%d, workers=%d)",
        len(worklist), len(already_cached), pending_strings, len(batches), batch_size, num_workers,
    )

    if not batches:
        log.info("nada a traduzir - worklist vazia ou tudo já está no cache.")
        db.export_to_json(cfg.paths.translation_memory_json, source_language=cfg.source_language, target_language=cfg.target_language)
        return 0

    llm = _DryRunLLM() if args.dry_run else LMStudioClient(cfg.llm)
    if not llm.ping():
        log.error(
            "não consegui falar com o LM Studio em %s (modelo esperado: %s). "
            "Confirme que o servidor local está rodando antes de iniciar o pipeline.",
            cfg.llm.base_url, cfg.llm.model,
        )
        return 1
    log.info("LM Studio acessível em %s (modelo=%s)", cfg.llm.base_url, cfg.llm.model)

    prompt_builder = PromptBuilder(glossary_terms)
    validator = BatchValidator(glossary_terms)
    metrics = Metrics(total_translatable=len(worklist), already_done=len(already_cached))

    work_queue = TranslationQueue(maxsize=cfg.pipeline.queue_maxsize)
    for batch in batches:
        work_queue.put(batch)
    work_queue.close(num_workers)

    stop_event = threading.Event()
    completed_batches = AtomicCounter()
    workers = [
        TranslationWorker(
            worker_id=i + 1,
            work_queue=work_queue,
            db=db,
            llm=llm,
            prompt_builder=prompt_builder,
            validator=validator,
            metrics=metrics,
            item_retry_limit=cfg.pipeline.item_retry_limit,
            stop_event=stop_event,
            on_batch_done=completed_batches.increment,
        )
        for i in range(num_workers)
    ]

    reporter = MetricsReporter(metrics, cfg.pipeline.metrics_interval_seconds)

    def _handle_sigint(signum, frame):  # noqa: ARG001
        if stop_event.is_set():
            log.warning("segundo Ctrl+C recebido - encerrando imediatamente sem esperar os workers")
            sys.exit(1)
        stop_event.set()
        log.warning(
            "interrupção recebida - cada worker termina o lote em andamento (já commitado) e para; "
            "lotes ainda não iniciados ficam pendentes para a próxima execução (Ctrl+C de novo força saída imediata)"
        )

    previous_handler = signal.signal(signal.SIGINT, _handle_sigint)

    for w in workers:
        w.start()
    reporter.start()

    try:
        last_export_batch_count = 0
        while any(w.is_alive() for w in workers):
            time.sleep(1.0)
            completed = completed_batches.value
            if completed - last_export_batch_count >= cfg.pipeline.export_every_n_batches:
                db.export_to_json(cfg.paths.translation_memory_json, source_language=cfg.source_language, target_language=cfg.target_language)
                last_export_batch_count = completed
    finally:
        signal.signal(signal.SIGINT, previous_handler)
        reporter.stop()
        reporter.join(timeout=5.0)
        for w in workers:
            w.join(timeout=5.0)
        db.export_to_json(cfg.paths.translation_memory_json, source_language=cfg.source_language, target_language=cfg.target_language)
        db.close()

    final_stats = metrics.snapshot()
    log.info(
        "execução concluída: %d traduzidas, %d p/ revisão, %d pendentes restantes, %d erro(s), %.1f str/min médio",
        final_stats.translated, final_stats.needs_review, final_stats.pending, final_stats.errors, final_stats.strings_per_min,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = load_config()
    configure_logging(cfg.paths.log_dir, level=logging.WARNING if args.quiet else logging.INFO)
    return run(cfg, args)


if __name__ == "__main__":
    raise SystemExit(main())
