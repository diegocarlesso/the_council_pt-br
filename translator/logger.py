"""
translator/logger.py

Logging centralizado do pipeline: console (nível INFO, para acompanhar em
tempo real) + arquivo rotativo diário em pt-br/logs/ (nível DEBUG, para
diagnosticar depois de uma execução de horas/dias sem supervisão).

O módulo logging da stdlib já é thread-safe (cada Handler serializa
escrita com um lock interno), então workers concorrentes podem logar
diretamente sem coordenação adicional.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

_CONFIGURED = False

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(threadName)-16s | %(name)s | %(message)s"


def configure_logging(log_dir: Path, level: int = logging.INFO) -> None:
    """Configura o logger raiz do pacote `translator`. Idempotente - chamar
    mais de uma vez (ex.: em testes) não duplica handlers."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(LOG_FORMAT)

    root = logging.getLogger("translator")
    root.setLevel(logging.DEBUG)
    root.propagate = False

    # O console do Windows (cmd/PowerShell legado) frequentemente usa uma
    # codepage que não é UTF-8 por padrão - sem isso, textos em pt-BR com
    # acento aparecem corrompidos (ou o handler lança UnicodeEncodeError e
    # derruba a mensagem de log). reconfigure() existe desde Python 3.7
    # para streams de texto; ignoramos silenciosamente se o stream não
    # suportar (ex.: stdout redirecionado para algo que não é TextIOWrapper).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_dir / "translator.log",
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"translator.{name}")
