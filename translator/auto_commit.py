"""
translator/auto_commit.py

Rotina de commit + push automático do progresso de tradução - roda em
paralelo ao pipeline (`python -m translator.translate`), como mais um
processo desacoplado, para o progresso não ficar dias só na máquina local
sem sincronizar com o repositório remoto.

A cada `--interval` segundos (padrão 1h):
  1. Exporta o SQLite (fonte de verdade em execução) -> translation_memory.json.
  2. Regenera pt-br/PROGRESS.md (reaproveita progress_report.py existente,
     não duplica a lógica de checkpoint).
  3. `git add` SÓ esses dois arquivos - nunca varre o resto do working
     tree (código, configs, etc. ficam de fora de propósito; mudanças aí
     continuam exigindo commit manual e deliberado).
  4. Commita (só se houver mudança de verdade) e dá push do branch atual
     para origin.

Falhas de rede/push não derrubam a rotina - ficam logadas e o commit
local permanece (é incluído no próximo push bem-sucedido, ou pode ser
empurrado manualmente).

Uso:
    python -m translator.auto_commit                   # a cada 1h até Ctrl+C
    python -m translator.auto_commit --interval 1800    # a cada 30 min
    python -m translator.auto_commit --once             # um ciclo e sai
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from .config import TranslatorConfig, load_config
from .dashboard import CorpusTotals, load_corpus_totals
from .database import TranslationMemoryDB, TranslationMemoryStats
from .logger import configure_logging, get_logger

log = get_logger("auto_commit")

TRACKED_FILES = ("pt-br/translation_memory.json", "pt-br/PROGRESS.md")


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _refresh_progress_report() -> None:
    """Reaproveita progress_report.py (módulo irmão, na raiz do projeto -
    já está em sys.path via config.py) em vez de duplicar a lógica de
    checkpoint aqui."""
    import progress_report

    progress_report.main()


def _current_branch(project_root: Path) -> str | None:
    result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], project_root)
    if result.returncode != 0:
        log.error("não consegui determinar o branch atual: %s", result.stderr.strip())
        return None
    return result.stdout.strip()


def _commit_message(totals: CorpusTotals, stats: TranslationMemoryStats) -> str:
    translated = min(stats.translated, totals.total_translatable)
    pct = (translated / totals.total_translatable * 100) if totals.total_translatable else 0.0
    return (
        f"chore: progresso automático - {translated}/{totals.total_translatable} ({pct:.1f}%)\n"
        f"\n"
        f"Exportado automaticamente do SQLite (translation_memory.db) por "
        f"translator/auto_commit.py.\n"
        f"\n"
        f"Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
    )


def run_cycle(cfg: TranslatorConfig, totals: CorpusTotals) -> bool:
    """Executa um ciclo completo. Retorna True se algo foi commitado e
    enviado ao remoto."""
    db = TranslationMemoryDB(cfg.paths.translation_memory_db)
    try:
        db.export_to_json(
            cfg.paths.translation_memory_json,
            source_language=cfg.source_language,
            target_language=cfg.target_language,
        )
        stats = db.stats()
    finally:
        db.close()

    try:
        _refresh_progress_report()
    except Exception:
        log.exception("falha ao regenerar PROGRESS.md - seguindo só com translation_memory.json")

    project_root = cfg.paths.project_root

    status = _run_git(["status", "--porcelain", "--", *TRACKED_FILES], project_root)
    if status.returncode != 0:
        log.error("git status falhou: %s", status.stderr.strip())
        return False
    if not status.stdout.strip():
        log.info("nada para commitar (%s sem mudanças)", ", ".join(TRACKED_FILES))
        return False

    add = _run_git(["add", "--", *TRACKED_FILES], project_root)
    if add.returncode != 0:
        log.error("git add falhou: %s", add.stderr.strip())
        return False

    commit = _run_git(["commit", "-m", _commit_message(totals, stats)], project_root)
    if commit.returncode != 0:
        log.error("git commit falhou: %s", commit.stderr.strip())
        return False
    log.info("commit criado: %s", commit.stdout.strip().splitlines()[0] if commit.stdout.strip() else "(ok)")

    branch = _current_branch(project_root)
    if branch is None:
        log.error("commit feito localmente, mas não consegui identificar o branch para dar push")
        return True

    push = _run_git(["push", "origin", branch], project_root)
    if push.returncode != 0:
        log.error(
            "git push falhou (commit continua local, será incluído no próximo push bem-sucedido): %s",
            push.stderr.strip(),
        )
        return True

    translated = min(stats.translated, totals.total_translatable)
    pct = (translated / totals.total_translatable * 100) if totals.total_translatable else 0.0
    log.info("push concluído -> origin/%s (%d/%d, %.1f%%)", branch, translated, totals.total_translatable, pct)
    return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--interval", type=float, default=3600.0, help="Segundos entre ciclos (padrão: 3600 = 1h)")
    parser.add_argument("--once", action="store_true", help="Executa um único ciclo e sai")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = load_config()
    configure_logging(cfg.paths.log_dir)

    if not cfg.paths.preprocessed_json.exists():
        log.error("%s não existe - rode preprocess.py primeiro.", cfg.paths.preprocessed_json)
        return 1
    if not cfg.paths.translation_memory_db.exists():
        log.error(
            "%s não existe ainda - rode `python -m translator.translate` pelo menos uma vez primeiro.",
            cfg.paths.translation_memory_db,
        )
        return 1

    totals = load_corpus_totals(cfg.paths.preprocessed_json)

    if args.once:
        run_cycle(cfg, totals)
        return 0

    log.info("rotina de commit automático iniciada - a cada %.0f min (Ctrl+C para parar; a tradução continua)", args.interval / 60)
    try:
        while True:
            try:
                run_cycle(cfg, totals)
            except Exception:
                log.exception("ciclo de commit automático falhou - tentando de novo no próximo intervalo")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        log.info("rotina de commit automático encerrada (Ctrl+C) - a tradução em si não é afetada")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
