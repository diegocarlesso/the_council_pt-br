"""
translator/utils.py

Utilitários compartilhados pelo pipeline. Reaproveita deliberadamente a
lógica de identificação/categorização já validada em preprocess.py
(canonical_id_for, category_for_file) em vez de duplicá-la - qualquer
canonical_id calculado aqui precisa continuar batendo byte-a-byte com o
que já está gravado em translation_memory.json.
"""
from __future__ import annotations

import json
import re
import threading
from typing import Any, Iterable, Iterator, TypeVar

from . import config  # noqa: F401 - garante PROJECT_ROOT em sys.path antes do import abaixo, não importa quem importa utils.py primeiro
# Reaproveita o pipeline existente em vez de reimplementar.
from preprocess import canonical_id_for, category_for_file  # noqa: F401

T = TypeVar("T")

# Mesmos padrões usados por preprocess.py/validate_batch.py - mantidos
# consistentes de propósito para que a validação deste pipeline concorde
# com a QA já existente em validate_batch.py.
FORMAT_PLACEHOLDER_RE = re.compile(r"%[a-zA-Z0-9]+")
BRACE_PLACEHOLDER_RE = re.compile(r"\{[^{}]*\}")
TAG_RE = re.compile(r"<[^>]+>")
COMMAND_RE = re.compile(r"\|\w+\([^)]*\)")
LINEBREAK_CHARS = ("\n", "\t", "\r")

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def chunked(items: list[T], size: int) -> Iterator[list[T]]:
    """Quebra uma lista em pedaços de até `size` itens, preservando ordem."""
    for i in range(0, len(items), size):
        yield items[i:i + size]


def extract_json_object(raw_text: str) -> dict[str, Any]:
    """Extrai um objeto JSON de uma resposta de LLM que pode vir cercada de
    texto solto ou de blocos de código markdown (comum em modelos locais
    menores, que nem sempre obedecem "responda somente JSON" à risca).

    Estratégia, da mais para a menos estrita:
      1. json.loads direto (caminho feliz, resposta já é JSON puro).
      2. Conteúdo dentro de um bloco ```json ... ``` ou ``` ... ```.
      3. Maior trecho entre a primeira '{' e a última '}' do texto.

    Lança json.JSONDecodeError se nenhuma estratégia produzir JSON válido -
    o chamador trata isso como "resposta inválida" e aciona retentativa.
    """
    text = raw_text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fence_match = _JSON_FENCE_RE.search(text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("não foi possível extrair um objeto JSON válido da resposta", text, 0)


def fit_to_byte_length(original: str, replacement: str) -> str:
    """Corta ou preenche com espaço à direita para bater exatamente o
    tamanho em bytes UTF-8 do original - necessário para o cluster de
    menu de boot (menu_boot_suspect, ver docs/04-RISCOS_TECNICOS.md do
    pipeline existente). Mesma lógica de translate_batch.py/validate_batch.py,
    mantida consistente de propósito."""
    orig_len = len(original.encode("utf-8"))
    rep_bytes = replacement.encode("utf-8")
    if len(rep_bytes) > orig_len:
        rep_bytes = rep_bytes[:orig_len]
        while rep_bytes and (rep_bytes[-1] & 0xC0) == 0x80:
            rep_bytes = rep_bytes[:-1]
    else:
        rep_bytes = rep_bytes + b" " * (orig_len - len(rep_bytes))
    return rep_bytes.decode("utf-8", errors="ignore")


def mechanical_signature(text: str) -> dict[str, Any]:
    """Conta placeholders/tags/comandos/quebras de linha de um texto -
    usado pelo validator para comparar original vs tradução."""
    return {
        "placeholders": sorted(FORMAT_PLACEHOLDER_RE.findall(text)),
        "braces": sorted(BRACE_PLACEHOLDER_RE.findall(text)),
        "tags": sorted(TAG_RE.findall(text)),
        "commands": sorted(COMMAND_RE.findall(text)),
        "linebreaks": {ch: text.count(ch) for ch in LINEBREAK_CHARS if ch in text},
    }


class AtomicCounter:
    """Contador inteiro thread-safe simples - usado para o produtor (thread
    principal) acompanhar quantos lotes já foram concluídos pelos workers
    sem inferir isso de queue.qsize() (que também conta os sentinels de
    desligamento e por isso não reflete lotes concluídos com precisão)."""

    def __init__(self) -> None:
        self._value = 0
        self._lock = threading.Lock()

    def increment(self) -> int:
        with self._lock:
            self._value += 1
            return self._value

    @property
    def value(self) -> int:
        with self._lock:
            return self._value


def dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
