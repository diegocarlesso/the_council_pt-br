"""
translator/queue.py

Fila de tradução entre o produtor (translate.py, que monta os lotes a
partir de preprocessed.json) e os workers (worker.py, que consultam o
LLM). Construída sobre queue.Queue da stdlib - já é thread-safe e
bloqueante do jeito certo (get() bloqueia a thread do worker, não o
processo inteiro; put() do produtor não bloqueia o programa esperando o
LLM responder, que é justamente o requisito de não travar a aplicação
enquanto se espera uma resposta do modelo).

Desligamento: um sentinel (None) é empilhado uma vez por worker ativo, e
cada worker termina seu loop ao recebê-lo - padrão "poison pill", evita
precisar de um Event/flag compartilhado só para isso.
"""
from __future__ import annotations

# Import absoluto de propósito (é o módulo `queue` da stdlib, não este
# arquivo) - só é seguro porque este pacote é sempre executado via
# `python -m translator.translate`/import de pacote, nunca com
# translator/ solto em sys.path (ver nota em config.py). Se este arquivo
# fosse rodado como script direto, translator/ entraria em sys.path[0] e
# este import resolveria para si mesmo.
import queue as _queue
from dataclasses import dataclass, field


@dataclass(frozen=True)
class WorkItem:
    canonical_id: str
    text: str
    usage_count: int = 0
    menu_boot_suspect: bool = False


@dataclass(frozen=True)
class Batch:
    batch_id: int
    category: str
    items: list[WorkItem] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.items)


class TranslationQueue:
    """Wrapper fino sobre queue.Queue[Batch | None] com desligamento
    explícito por sentinel."""

    def __init__(self, maxsize: int = 0) -> None:
        self._queue: _queue.Queue = _queue.Queue(maxsize=maxsize)

    def put(self, batch: Batch) -> None:
        self._queue.put(batch)

    def get(self) -> Batch | None:
        """Bloqueia até haver um lote ou o sinal de desligamento (None)."""
        return self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    def close(self, num_workers: int) -> None:
        """Sinaliza todos os workers para terminarem após esvaziar a fila."""
        for _ in range(num_workers):
            self._queue.put(None)

    def qsize(self) -> int:
        return self._queue.qsize()

    def join(self) -> None:
        self._queue.join()
