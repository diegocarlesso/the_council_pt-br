"""
translator/config.py

Configuração central do pipeline de tradução automática (LM Studio local).

Todos os caminhos são resolvidos a partir da raiz do projeto (o diretório
que contém preprocess.py, dump_texts.py, translation_memory.json etc. -
Data/Packages/), independente de onde o script for chamado, e todo valor
pode ser sobrescrito por variável de ambiente (prefixo TRANSLATOR_) sem
tocar em código - útil para rodar em outra máquina, apontar para outro
modelo do LM Studio, ou ajustar concorrência sem editar fonte.

Este módulo também garante que PROJECT_ROOT esteja em sys.path, para que
o resto do pacote possa reaproveitar preprocess.py (canonical_id_for,
category_for_file) em vez de duplicar essa lógica - ver 01-README do
pipeline existente.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Raiz do projeto (Data/Packages/) - pai deste pacote translator/.
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Garante que `import preprocess` (módulo irmão, fora do pacote
# translator/) funcione mesmo se o processo for iniciado de outro
# diretório de trabalho.
#
# NOTA sobre como rodar este pacote: sempre via `python -m
# translator.translate` (a partir de Data/Packages) ou importando
# `translator.*` de outro código - nunca executando um arquivo dentro de
# translator/ diretamente como script (`python translator/translate.py`).
# Rodar como script solto faz o próprio interpretador inserir translator/
# em sys.path[0], o que sombrearia módulos da stdlib com o mesmo nome de
# arquivos deste pacote (em particular, translator/queue.py sombrearia o
# `queue` da stdlib). Os módulos deste pacote usam import relativo entre
# si (`from .config import ...`) exatamente para não depender de
# translator/ estar solto no sys.path.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _env_str(name: str, default: str) -> str:
    return os.environ.get(f"TRANSLATOR_{name}", default)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(f"TRANSLATOR_{name}")
    return int(raw) if raw is not None else default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(f"TRANSLATOR_{name}")
    return float(raw) if raw is not None else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(f"TRANSLATOR_{name}")
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class PathsConfig:
    """Caminhos de entrada/saída do pipeline, todos relativos a PROJECT_ROOT."""

    project_root: Path = PROJECT_ROOT
    preprocessed_json: Path = PROJECT_ROOT / "preprocessed.json"
    glossary_json: Path = PROJECT_ROOT / "pt-br" / "glossary.json"
    translation_memory_json: Path = PROJECT_ROOT / "pt-br" / "translation_memory.json"
    translation_memory_db: Path = PROJECT_ROOT / "pt-br" / "translation_memory.db"
    log_dir: Path = PROJECT_ROOT / "pt-br" / "logs"


@dataclass(frozen=True)
class LLMConfig:
    """Parâmetros de conexão e geração do backend LM Studio (OpenAI-compatible)."""

    base_url: str = field(default_factory=lambda: _env_str("LM_STUDIO_URL", "http://127.0.0.1:1234/v1"))
    model: str = field(default_factory=lambda: _env_str("MODEL_NAME", "qwen2.5-7b-instruct-1m"))

    connect_timeout: float = field(default_factory=lambda: _env_float("CONNECT_TIMEOUT", 10.0))

    # O timeout de LEITURA é dinâmico, não uma constante fixa: um modelo
    # local de 7B gerando a tradução de um lote inteiro (não só 1 string)
    # pode legitimamente levar minutos, e o tempo cresce com a quantidade
    # de itens do lote (confirmado na prática: ~7s/item para lotes
    # pequenos em hardware modesto - um lote de 40 pode passar de 4-5
    # minutos tranquilamente, o que já estourava um timeout fixo de 180s e
    # fazia o pipeline inteiro ficar preso num loop de timeout->retry sem
    # nunca completar). LMStudioClient.translate() calcula o timeout
    # efetivo como base_read_timeout + seconds_per_item_timeout * N itens
    # do lote - generoso o bastante para lotes grandes sem penalizar
    # retentativas de 1 item só (que herdam apenas o piso).
    base_read_timeout: float = field(default_factory=lambda: _env_float("BASE_READ_TIMEOUT", 90.0))
    seconds_per_item_timeout: float = field(default_factory=lambda: _env_float("SECONDS_PER_ITEM_TIMEOUT", 20.0))

    # Duas classes de falha, dois orçamentos de retentativa (backoff
    # exponencial com jitter em ambos - não confundir com as retentativas
    # de item por falha de VALIDAÇÃO, essas ficam em PipelineConfig):
    #
    # 1) Perda de CONEXÃO (servidor fora do ar, timeout de conexão, HTTP
    #    5xx) - o cenário normal de "LM Studio foi reiniciado" ou "o PC
    #    estava suspenso" numa execução de dias. Orçamento generoso: o
    #    pipeline deve esperar pacientemente o servidor voltar, nunca
    #    marcar um lote como needs_review só porque o servidor estava
    #    temporariamente indisponível.
    max_connection_retries: int = field(default_factory=lambda: _env_int("MAX_CONNECTION_RETRIES", 60))
    # Timeout de LEITURA é um caso à parte dentro da classe "conexão": ao
    # contrário de conexão recusada (falha em milissegundos, barato
    # retentar 60x), um timeout só acontece depois de esperar o timeout
    # INTEIRO (que já escala com o tamanho do lote, ver
    # base_read_timeout/seconds_per_item_timeout acima) - retentar o
    # mesmo lote grande de novo e de novo é caro e raramente ajuda (se o
    # modelo não terminou em ~90s+20s/item, provavelmente não é sorte de
    # rede). Orçamento pequeno aqui; depois disso o erro sobe para o loop
    # de retry por item do worker (que tenta de novo um número limitado
    # de vezes antes de marcar needs_review).
    max_timeout_retries: int = field(default_factory=lambda: _env_int("MAX_TIMEOUT_RETRIES", 2))
    # 2) Resposta INVÁLIDA com o servidor respondendo normalmente (corpo
    #    não é JSON, HTTP 200 mas sem "choices", etc.) - sinal de que algo
    #    está sistematicamente errado com esta requisição; orçamento curto,
    #    depois disso é melhor render-se e marcar needs_review para revisão
    #    humana do que insistir indefinidamente.
    max_response_retries: int = field(default_factory=lambda: _env_int("MAX_RESPONSE_RETRIES", 5))

    backoff_base_seconds: float = field(default_factory=lambda: _env_float("BACKOFF_BASE", 1.5))
    backoff_max_seconds: float = field(default_factory=lambda: _env_float("BACKOFF_MAX", 60.0))

    temperature: float = field(default_factory=lambda: _env_float("TEMPERATURE", 0.15))
    top_p: float = field(default_factory=lambda: _env_float("TOP_P", 0.90))
    # 8192 dá folga para lotes de batch_size=40 com strings de diálogo mais
    # longas - 4096 arriscava finish_reason=length (resposta truncada,
    # tratada como erro e reenviada) em lotes com várias falas compridas.
    max_tokens: int = field(default_factory=lambda: _env_int("MAX_TOKENS", 8192))

    # Desligado por padrão: o backend real por trás do LM Studio (llama.cpp)
    # frequentemente só aceita response_format.type="json_schema" ou "text",
    # não "json_object" (confirmado contra qwen2.5-7b-instruct-1m - HTTP 400
    # "'response_format.type' must be 'json_schema' or 'text'"). Em vez de
    # depender de um recurso específico de versão de servidor, confiamos na
    # instrução do prompt ("responda SOMENTE com JSON") + no parser
    # tolerante (utils.extract_json_object, que lida com cercas markdown e
    # texto solto ao redor do JSON) - mais portável entre builds. Pode ser
    # ligado via TRANSLATOR_JSON_MODE=1 se o seu servidor suportar
    # json_object de verdade; o cliente também se autodesliga sozinho no
    # primeiro HTTP 400 relacionado, então ligar não quebra nada, só tenta.
    request_json_mode: bool = field(default_factory=lambda: _env_bool("JSON_MODE", False))


@dataclass(frozen=True)
class PipelineConfig:
    """Parâmetros de lote, fila, workers e tolerância a falhas."""

    batch_size: int = field(default_factory=lambda: _env_int("BATCH_SIZE", 40))
    num_workers: int = field(default_factory=lambda: _env_int("NUM_WORKERS", 2))

    # Quantas vezes reenviar SÓ os itens que falharam validação (subconjunto
    # cada vez menor do lote) antes de desistir e marcar needs_review.
    item_retry_limit: int = field(default_factory=lambda: _env_int("ITEM_RETRY_LIMIT", 3))

    # Tamanho máximo da fila de lotes pendentes (0 = ilimitado). Limitar
    # evita acumular memória se os workers ficarem para trás em corpora
    # muito maiores que o de The Council.
    queue_maxsize: int = field(default_factory=lambda: _env_int("QUEUE_MAXSIZE", 0))

    metrics_interval_seconds: float = field(default_factory=lambda: _env_float("METRICS_INTERVAL", 15.0))

    # Exporta a TM (SQLite -> translation_memory.json) a cada N lotes
    # concluídos, além de sempre exportar ao final/interrupção.
    export_every_n_batches: int = field(default_factory=lambda: _env_int("EXPORT_EVERY_N_BATCHES", 10))


@dataclass(frozen=True)
class TranslatorConfig:
    paths: PathsConfig = field(default_factory=PathsConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    source_language: str = "en"
    target_language: str = "pt-BR"


def load_config() -> TranslatorConfig:
    """Ponto único de carregamento de configuração (env vars já aplicadas
    via default_factory de cada campo)."""
    cfg = TranslatorConfig()
    cfg.paths.log_dir.mkdir(parents=True, exist_ok=True)
    return cfg
