"""
translator/dashboard.py

Painel de monitoramento standalone - roda como processo separado do
pipeline (`python -m translator.dashboard`), só LÊ o banco (SQLite em modo
WAL permite leitores concorrentes sem atrapalhar os workers que estão
escrevendo) e o preprocessed.json (uma vez, no início). Não consome nada
do worker/fila/LLM - é seguro deixar aberto o tempo todo, em outro
terminal, enquanto `python -m translator.translate` roda em segundo plano
por dias.

Uso:
    python -m translator.dashboard                # atualiza a cada 5s até Ctrl+C
    python -m translator.dashboard --interval 15
    python -m translator.dashboard --once          # imprime um snapshot e sai (bom para scripts/log)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter, deque
from dataclasses import dataclass

from .config import load_config
from .database import TranslationMemoryDB

BAR_WIDTH = 40


@dataclass
class CorpusTotals:
    total_translatable: int
    by_category: dict[str, int]


def load_corpus_totals(preprocessed_path) -> CorpusTotals:
    """Lê preprocessed.json UMA VEZ (é grande, ~27MB no corpus de The
    Council) para saber o universo total de strings traduzíveis e a
    distribuição por categoria - isso não muda durante uma execução do
    pipeline, então não há motivo para reler a cada refresh do painel."""
    with open(preprocessed_path, encoding="utf-8") as f:
        data = json.load(f)
    canonical = data["_canonical"]
    by_category = Counter(
        entry["primary_category"] for entry in canonical.values() if entry["translatable"]
    )
    total = sum(by_category.values())
    return CorpusTotals(total_translatable=total, by_category=dict(by_category))


def _format_duration(seconds: float | None) -> str:
    if seconds is None or seconds == float("inf") or seconds != seconds:  # NaN check
        return "indeterminado"
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if days:
        return f"{days}d{hours:02d}h{minutes:02d}m"
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{seconds:02d}s"
    return f"{seconds}s"


def _progress_bar(fraction: float, width: int = BAR_WIDTH) -> str:
    fraction = max(0.0, min(1.0, fraction))
    filled = int(round(fraction * width))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


class SpeedTracker:
    """Velocidade média numa janela por TEMPO (não por número de amostras):
    com um modelo local, um lote de 40 strings pode levar vários minutos
    para fechar - uma janela de "últimas N amostras" com refresh de poucos
    segundos cobre menos de 1 minuto de histórico e fica em 0.0 quase o
    tempo todo (some da tela bem antes do próximo lote fechar), dando a
    falsa impressão de que travou. Aqui a janela é em segundos: guardamos
    amostras e descartamos as mais velhas que `window_seconds`, então a
    janela sempre cobre tempo suficiente para pegar pelo menos um lote
    fechando, não importa o intervalo de refresh do painel."""

    def __init__(self, window_seconds: float = 900.0) -> None:
        self.window_seconds = window_seconds
        self._samples: deque[tuple[float, int]] = deque()

    def add_sample(self, translated: int) -> None:
        now = time.monotonic()
        self._samples.append((now, translated))
        cutoff = now - self.window_seconds
        while len(self._samples) > 1 and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def strings_per_min(self) -> float | None:
        """None enquanto não há amostras suficientes cobrindo tempo
        suficiente para uma estimativa confiável (painel recém-aberto) -
        o chamador deve mostrar algo como "calculando..." nesse caso, não
        0.0 (que parece "travado")."""
        if len(self._samples) < 2:
            return None
        t0, n0 = self._samples[0]
        t1, n1 = self._samples[-1]
        elapsed = t1 - t0
        if elapsed < 30:  # menos de 30s de histórico ainda não é confiável
            return None
        return (n1 - n0) / elapsed * 60.0


def render(totals: CorpusTotals, db: TranslationMemoryDB, speed: SpeedTracker, started_at: float) -> str:
    stats = db.stats()
    translated = min(stats.translated, totals.total_translatable)
    pending = max(0, totals.total_translatable - translated)
    fraction = (translated / totals.total_translatable) if totals.total_translatable else 0.0

    speed.add_sample(translated)
    rate = speed.strings_per_min()
    eta = (pending / rate) * 60 if rate else None
    rate_display = f"{rate:.1f} strings/min" if rate is not None else "calculando... (abra o painel por alguns minutos)"

    lines = []
    lines.append("=" * 70)
    lines.append("THE COUNCIL - PAINEL DE TRADUÇÃO PT-BR (LM Studio local)")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"{_progress_bar(fraction)}  {fraction:6.1%}")
    lines.append(f"Traduzidas: {translated:,} / {totals.total_translatable:,}   Pendentes: {pending:,}".replace(",", "."))
    lines.append("")
    lines.append(f"Status no banco -> aprovadas: {stats.approved:,}  rascunho: {stats.draft:,}  "
                  f"p/revisão: {stats.needs_review:,}".replace(",", "."))
    lines.append(f"Velocidade (janela de {speed.window_seconds / 60:.0f}min): {rate_display}   ETA: {_format_duration(eta)}")
    lines.append(f"Painel aberto há: {_format_duration(time.monotonic() - started_at)}")
    lines.append("")
    lines.append("Por categoria (traduzidas / total):")
    for category, cat_total in sorted(totals.by_category.items(), key=lambda kv: -kv[1]):
        cat_done = stats.by_category.get(category, 0)
        cat_done = min(cat_done, cat_total)
        cat_fraction = (cat_done / cat_total) if cat_total else 0.0
        lines.append(f"  {category:<14} {_progress_bar(cat_fraction, 24)} {cat_fraction:6.1%}  "
                      f"({cat_done:,}/{cat_total:,})".replace(",", "."))
    if stats.needs_review:
        lines.append("")
        lines.append(
            f"⚠ {stats.needs_review} string(s) marcadas needs_review - precisam de revisão manual "
            f"(o pipeline não trava por causa delas, mas elas não contam como concluídas de verdade)."
        )
    lines.append("")
    lines.append(f"Atualizado em {time.strftime('%Y-%m-%d %H:%M:%S')} - Ctrl+C para sair (isto não afeta o pipeline)")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--interval", type=float, default=5.0, help="Segundos entre atualizações (padrão: 5)")
    parser.add_argument("--once", action="store_true", help="Imprime um snapshot e sai, sem loop")
    parser.add_argument("--no-clear", action="store_true", help="Não limpa a tela entre atualizações (útil para redirecionar a um arquivo)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    args = parse_args(argv)
    cfg = load_config()

    if not cfg.paths.preprocessed_json.exists():
        print(f"Erro: {cfg.paths.preprocessed_json} não existe.", file=sys.stderr)
        return 1
    if not cfg.paths.translation_memory_db.exists():
        print(
            f"Erro: {cfg.paths.translation_memory_db} não existe ainda - rode "
            f"`python -m translator.translate` pelo menos uma vez primeiro (ele cria e migra o banco).",
            file=sys.stderr,
        )
        return 1

    print("Carregando totais do corpus (preprocessed.json)...")
    totals = load_corpus_totals(cfg.paths.preprocessed_json)

    db = TranslationMemoryDB(cfg.paths.translation_memory_db)
    speed = SpeedTracker()
    started_at = time.monotonic()

    try:
        if args.once:
            print(render(totals, db, speed, started_at))
            return 0

        while True:
            output = render(totals, db, speed, started_at)
            if not args.no_clear:
                os.system("cls" if os.name == "nt" else "clear")
            print(output)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nPainel encerrado (o pipeline de tradução continua rodando normalmente).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
