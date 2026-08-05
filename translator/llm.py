"""
translator/llm.py

Camada isolada de comunicação com o backend de LLM. Todo o resto do
pipeline fala com a interface abstrata LLMBackend, nunca com requests
diretamente - trocar de backend no futuro (outro servidor OpenAI-compatible,
outro modelo) significa escrever uma nova subclasse aqui, sem tocar em
prompt.py/worker.py/translate.py.

Implementação concreta: LMStudioClient, contra o endpoint OpenAI-compatible
do LM Studio (http://127.0.0.1:1234/v1/chat/completions). Não usa OpenAI,
Gemini, OpenRouter ou a API da Anthropic - só o servidor local.
"""
from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter

from .config import LLMConfig
from .logger import get_logger

log = get_logger("llm")


class LLMError(Exception):
    """Erro genérico de comunicação/resposta do backend de LLM."""


class LLMConnectionError(LLMError):
    """Falha de transporte: conexão recusada, timeout, HTTP 5xx."""


class LLMResponseError(LLMError):
    """A conexão funcionou, mas o corpo da resposta é inválido: JSON
    malformado, campo esperado ausente, ou resposta truncada
    (finish_reason == "length")."""


@dataclass
class LLMResult:
    content: str
    usage: dict | None  # {"prompt_tokens", "completion_tokens", "total_tokens"} quando disponível
    model: str


class LLMBackend(ABC):
    """Interface que qualquer backend de tradução deve implementar."""

    @abstractmethod
    def translate(self, system_prompt: str, user_content: str, *, item_count: int = 1) -> LLMResult:
        """Envia um prompt de sistema + conteúdo do lote, retorna o texto
        bruto da resposta (espera-se JSON) e metadados de uso. `item_count`
        (quantas strings o lote contém) é usado para calcular um timeout de
        leitura proporcional ao tamanho do trabalho pedido ao modelo."""

    @abstractmethod
    def ping(self) -> bool:
        """Verifica se o backend está acessível. Não lança - retorna bool."""


class LMStudioClient(LLMBackend):
    """Cliente para o endpoint OpenAI-compatible do LM Studio.

    Reaproveita uma única requests.Session (pool de conexões HTTP mantido
    vivo entre chamadas - custo de handshake pago uma vez, não a cada
    lote). A Session é compartilhada entre threads de worker: o pool de
    conexões do urllib3 por baixo do HTTPAdapter é thread-safe para esse
    uso (múltiplas threads chamando .post() concorrentemente); o que NÃO
    é seguro é mutar a Session (montar adapters, mexer em headers
    default) depois de start - e este cliente não faz isso após o
    __init__, então não há necessidade de lock adicional aqui.
    """

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.chat_url = f"{config.base_url.rstrip('/')}/chat/completions"
        self.models_url = f"{config.base_url.rstrip('/')}/models"

        self.session = requests.Session()
        adapter = HTTPAdapter(pool_connections=32, pool_maxsize=32)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Desligado automaticamente se o servidor rejeitar o parâmetro
        # (nem todo build do LM Studio/llama.cpp aceita response_format).
        self._json_mode_enabled = config.request_json_mode

    # ------------------------------------------------------------------

    def ping(self) -> bool:
        try:
            resp = self.session.get(self.models_url, timeout=(self.config.connect_timeout, 10.0))
            return resp.status_code == 200
        except requests.exceptions.RequestException as e:
            log.warning("ping ao LM Studio (%s) falhou: %s", self.models_url, e)
            return False

    def translate(self, system_prompt: str, user_content: str, *, item_count: int = 1) -> LLMResult:
        read_timeout = self.config.base_read_timeout + self.config.seconds_per_item_timeout * max(1, item_count)
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "max_tokens": self.config.max_tokens,
        }
        if self._json_mode_enabled:
            payload["response_format"] = {"type": "json_object"}

        data = self._post_with_retry(payload, read_timeout)

        try:
            choice = data["choices"][0]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMResponseError(f"resposta sem 'choices' válido: {data!r}") from e

        finish_reason = choice.get("finish_reason")
        content = (choice.get("message") or {}).get("content", "")

        if finish_reason == "length":
            raise LLMResponseError(
                "resposta truncada pelo modelo (finish_reason=length) - "
                "lote grande demais para max_tokens, reduza batch_size ou aumente max_tokens"
            )
        if not content or not content.strip():
            raise LLMResponseError("resposta vazia do modelo")

        return LLMResult(content=content, usage=data.get("usage"), model=data.get("model", self.config.model))

    # ------------------------------------------------------------------

    def _backoff_seconds(self, attempt: int) -> float:
        base = self.config.backoff_base_seconds * (2 ** (attempt - 1))
        capped = min(base, self.config.backoff_max_seconds)
        return capped + random.uniform(0, self.config.backoff_base_seconds)

    def _post_with_retry(self, payload: dict, read_timeout: float) -> dict:
        """Dois contadores de tentativa independentes: `connection_attempt`
        (perda de conexão/timeout/5xx - orçamento generoso, é o cenário
        esperado de "LM Studio foi reiniciado" numa execução de dias) e
        `response_attempt` (servidor respondeu mas o corpo é inválido -
        orçamento curto, sinal de problema sistemático, não vale insistir
        por horas)."""
        last_error: Exception | None = None
        connection_attempt = 0
        timeout_attempt = 0
        response_attempt = 0
        max_connection_attempts = max(1, self.config.max_connection_retries)
        max_timeout_attempts = max(1, self.config.max_timeout_retries)
        max_response_attempts = max(1, self.config.max_response_retries)

        while True:
            try:
                resp = self.session.post(
                    self.chat_url,
                    json=payload,
                    timeout=(self.config.connect_timeout, read_timeout),
                )
            except requests.exceptions.ConnectionError as e:
                connection_attempt += 1
                last_error = e
                if connection_attempt >= max_connection_attempts:
                    break
                log.warning(
                    "perda de conexão com LM Studio (tentativa %d/%d) - "
                    "servidor pode estar reiniciando, aguardando: %s",
                    connection_attempt, max_connection_attempts, e,
                )
                self._sleep_backoff(connection_attempt)
                continue
            except requests.exceptions.Timeout as e:
                # Orçamento próprio (pequeno) - cada tentativa aqui já
                # custou o read_timeout inteiro (dezenas de segundos a
                # minutos, escala com o tamanho do lote), diferente de
                # ConnectionError que falha quase instantaneamente.
                timeout_attempt += 1
                last_error = e
                if timeout_attempt >= max_timeout_attempts:
                    break
                log.warning(
                    "timeout aguardando LM Studio após %.0fs (tentativa %d/%d) - modelo local pode estar "
                    "sobrecarregado para o tamanho deste lote: %s",
                    read_timeout, timeout_attempt, max_timeout_attempts, e,
                )
                self._sleep_backoff(timeout_attempt)
                continue
            except requests.exceptions.RequestException as e:
                connection_attempt += 1
                last_error = e
                if connection_attempt >= max_connection_attempts:
                    break
                log.warning("erro de transporte com LM Studio (tentativa %d/%d): %s", connection_attempt, max_connection_attempts, e)
                self._sleep_backoff(connection_attempt)
                continue

            if resp.status_code == 400 and "response_format" in payload:
                # Checagem em cima do próprio `payload` local, não da flag
                # compartilhada `self._json_mode_enabled`: com workers
                # concorrentes, outra thread pode já ter desligado a flag
                # global entre o momento em que ESTA requisição foi montada
                # e a resposta 400 chegar - se não checássemos o payload em
                # si, essa requisição cairia direto em erro fatal em vez de
                # ser corrigida e reenviada.
                if self._json_mode_enabled:
                    log.warning("LM Studio rejeitou response_format=json_object (HTTP 400) - desligando json_mode para as próximas requisições")
                    self._json_mode_enabled = False
                payload = {k: v for k, v in payload.items() if k != "response_format"}
                continue  # tentativa imediata, não consome nenhum dos dois orçamentos

            if resp.status_code >= 500:
                connection_attempt += 1
                last_error = LLMConnectionError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                if connection_attempt >= max_connection_attempts:
                    break
                log.warning("LM Studio retornou %d (tentativa %d/%d)", resp.status_code, connection_attempt, max_connection_attempts)
                self._sleep_backoff(connection_attempt)
                continue

            if resp.status_code != 200:
                raise LLMResponseError(f"HTTP {resp.status_code} do LM Studio: {resp.text[:500]}")

            try:
                return resp.json()
            except ValueError as e:
                response_attempt += 1
                last_error = LLMResponseError(f"corpo da resposta não é JSON válido: {e}")
                if response_attempt >= max_response_attempts:
                    break
                log.warning(
                    "JSON inválido na resposta do LM Studio (tentativa %d/%d): %s",
                    response_attempt, max_response_attempts, e,
                )
                self._sleep_backoff(response_attempt)
                continue

        raise LLMConnectionError(f"falha ao falar com LM Studio: {last_error}") from last_error

    def _sleep_backoff(self, attempt: int) -> None:
        time.sleep(self._backoff_seconds(attempt))
