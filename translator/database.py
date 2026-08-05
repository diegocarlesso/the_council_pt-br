"""
translator/database.py

Única porta de entrada para SQLite no pipeline - nenhum outro módulo deve
importar sqlite3 diretamente. Implementa a memória de tradução persistente
(pt-br/translation_memory.db) que substitui o uso de
translation_memory.json como armazenamento de trabalho: o JSON continua
existindo como formato de troca com o resto do pipeline (validate_batch.py,
progress_report.py), mas quem lê/escreve a cada string durante a tradução
automática é este banco.

Concorrência: cada thread (cada TranslationWorker) recebe sua própria
conexão SQLite (thread-local) - conexões sqlite3 não são seguras para uso
concorrente entre threads. Leituras (get_cached/get_many_cached) não
precisam de lock: em modo WAL, leitores nunca bloqueiam nem são bloqueados
por um escritor. Escritas (upsert_many) são serializadas por um
threading.Lock de instância - o SQLite em si só permite um escritor por
vez de qualquer forma, então o lock evita que threads fiquem re-tentando
em cima de "database is locked" e torna o custo de contenção explícito e
previsível em vez de depender só do busy_timeout do driver.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .logger import get_logger

log = get_logger("database")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS translations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_id  TEXT UNIQUE NOT NULL,
    source        TEXT NOT NULL,
    target        TEXT DEFAULT '',
    context       TEXT,
    category      TEXT,
    status        TEXT NOT NULL DEFAULT 'pending',
    usage_count   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_translations_status ON translations(status);
CREATE INDEX IF NOT EXISTS idx_translations_category ON translations(category);
"""

# Status possíveis: draft, approved (herdados do fluxo manual existente),
# needs_review (esgotou retentativas de validação nesta pipeline).
_PROTECTED_STATUS = "approved"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TranslationEntry:
    """Representa uma linha de translations - espelha o schema da tabela
    e o schema de entries em translation_memory.json."""

    canonical_id: str
    source: str
    target: str
    category: str | None = None
    status: str = "draft"
    usage_count: int = 0
    context: str | None = None


@dataclass
class TranslationMemoryStats:
    total: int = 0
    approved: int = 0
    draft: int = 0
    needs_review: int = 0
    translated: int = 0  # target não vazio, qualquer status
    by_category: dict[str, int] = field(default_factory=dict)


class TranslationMemoryDB:
    """Wrapper único de acesso a pt-br/translation_memory.db."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Conexão (thread-local)
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    @property
    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._connect()
            self._local.conn = conn
        return conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def close_current_thread_connection(self) -> None:
        """Fecha a conexão da thread atual, se houver. Chamar ao final de
        cada worker para não deixar conexões penduradas quando a thread
        termina antes do processo (evita vazamento de descritores em
        execuções longas com muitos ciclos de start/stop)."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def close(self) -> None:
        self.close_current_thread_connection()

    def __enter__(self) -> "TranslationMemoryDB":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Leitura (sem lock - WAL permite leitura concorrente com escrita)
    # ------------------------------------------------------------------

    def get_cached(self, canonical_id: str) -> str | None:
        """Retorna a tradução já resolvida (draft ou approved) para este
        canonical_id, ou None se ainda não foi traduzido. Usado como
        cache antes de mandar qualquer coisa para o LLM."""
        row = self._conn.execute(
            "SELECT target FROM translations WHERE canonical_id = ? AND target IS NOT NULL AND target != ''",
            (canonical_id,),
        ).fetchone()
        return row["target"] if row is not None else None

    def get_many_cached(self, canonical_ids: list[str]) -> dict[str, str]:
        """Versão em lote de get_cached - evita uma query por string ao
        montar o worklist inicial (dezenas de milhares de strings)."""
        if not canonical_ids:
            return {}
        result: dict[str, str] = {}
        conn = self._conn
        # SQLite tem limite de variáveis por statement (default 999/32766
        # dependendo do build) - consulta em blocos para corpora grandes.
        for block_start in range(0, len(canonical_ids), 500):
            block = canonical_ids[block_start:block_start + 500]
            placeholders = ",".join("?" * len(block))
            rows = conn.execute(
                f"SELECT canonical_id, target FROM translations "
                f"WHERE canonical_id IN ({placeholders}) AND target IS NOT NULL AND target != ''",
                block,
            ).fetchall()
            for row in rows:
                result[row["canonical_id"]] = row["target"]
        return result

    def stats(self) -> TranslationMemoryStats:
        conn = self._conn
        stats = TranslationMemoryStats()
        row = conn.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) AS approved, "
            "SUM(CASE WHEN status = 'draft' THEN 1 ELSE 0 END) AS draft, "
            "SUM(CASE WHEN status = 'needs_review' THEN 1 ELSE 0 END) AS needs_review, "
            "SUM(CASE WHEN target IS NOT NULL AND target != '' THEN 1 ELSE 0 END) AS translated "
            "FROM translations"
        ).fetchone()
        stats.total = row["total"] or 0
        stats.approved = row["approved"] or 0
        stats.draft = row["draft"] or 0
        stats.needs_review = row["needs_review"] or 0
        stats.translated = row["translated"] or 0
        for cat_row in conn.execute(
            "SELECT category, COUNT(*) AS n FROM translations GROUP BY category"
        ):
            stats.by_category[cat_row["category"] or "(sem categoria)"] = cat_row["n"]
        return stats

    # ------------------------------------------------------------------
    # Escrita (serializada por _write_lock)
    # ------------------------------------------------------------------

    def upsert_many(self, entries: list[TranslationEntry]) -> int:
        """Grava um lote de traduções em uma única transação. Nunca
        sobrescreve uma linha com status='approved' (mesma regra do
        validate_batch.py existente - aprovação humana é definitiva).
        Retorna quantas linhas foram de fato inseridas/atualizadas."""
        if not entries:
            return 0
        now = _now()
        rows = [
            (
                e.canonical_id, e.source, e.target, e.context, e.category,
                e.status, e.usage_count, now, now,
            )
            for e in entries
        ]
        with self._write_lock:
            conn = self._conn
            cur = conn.executemany(
                """
                INSERT INTO translations
                    (canonical_id, source, target, context, category, status, usage_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(canonical_id) DO UPDATE SET
                    target = excluded.target,
                    context = excluded.context,
                    category = excluded.category,
                    status = excluded.status,
                    usage_count = excluded.usage_count,
                    updated_at = excluded.updated_at
                WHERE translations.status IS NOT 'approved'
                """,
                rows,
            )
            conn.commit()
            return cur.rowcount

    # ------------------------------------------------------------------
    # Migração JSON <-> SQLite
    # ------------------------------------------------------------------

    def import_from_json_if_empty(self, json_path: Path) -> int:
        """Se a tabela estiver vazia e translation_memory.json existir,
        importa todas as entradas para o banco. Idempotente: não faz nada
        se já houver qualquer linha (mesmo que o JSON tenha entradas
        novas - nesse caso use export/import manual, não é o caminho
        automático)."""
        existing = self._conn.execute("SELECT COUNT(*) AS n FROM translations").fetchone()["n"]
        if existing > 0:
            log.debug("banco já contém %d linhas - pulando migração automática do JSON", existing)
            return 0
        json_path = Path(json_path)
        if not json_path.exists():
            log.info("nenhum %s encontrado - iniciando banco vazio", json_path)
            return 0

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        entries = [
            TranslationEntry(
                canonical_id=item["canonical_id"],
                source=item.get("source", ""),
                target=item.get("target", "") or "",
                category=item.get("category"),
                status=item.get("status", "draft"),
                usage_count=item.get("usage_count", 0),
                context=item.get("context"),
            )
            for item in data.get("entries", [])
            if "canonical_id" in item
        ]
        count = self.upsert_many(entries)
        log.info("migração automática: %d entradas importadas de %s para %s", count, json_path, self.db_path)
        return count

    def export_to_json(
        self,
        json_path: Path,
        *,
        version: str = "1.0",
        source_language: str = "en",
        target_language: str = "pt-BR",
    ) -> int:
        """Exporta o conteúdo do banco de volta para o formato de
        translation_memory.json, para manter validate_batch.py e
        progress_report.py funcionando sem alteração. Escrita atômica
        (arquivo temporário + os.replace) para nunca deixar o JSON
        corrompido/truncado se o processo for interrompido no meio de uma
        execução de dias."""
        rows = self._conn.execute(
            "SELECT canonical_id, source, target, context, category, status, usage_count "
            "FROM translations ORDER BY canonical_id"
        ).fetchall()
        entries = [
            {
                "canonical_id": row["canonical_id"],
                "source": row["source"],
                "target": row["target"],
                "context": row["context"] if row["context"] is not None else row["category"],
                "category": row["category"],
                "status": row["status"],
                "usage_count": row["usage_count"],
            }
            for row in rows
        ]
        payload = {
            "version": version,
            "source_language": source_language,
            "target_language": target_language,
            "entries": entries,
        }

        json_path = Path(json_path)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=json_path.parent, prefix=".tmp_tm_export_", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, json_path)
        except BaseException:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
        log.info("exportado %d entradas -> %s", len(entries), json_path)
        return len(entries)
