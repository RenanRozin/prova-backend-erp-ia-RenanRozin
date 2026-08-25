"""Logging estruturado em JSON.

Log em JSON porque em produção quem lê não é humano, é o coletor (Loki, CloudWatch,
ELK). Texto livre custa caro para indexar e é impossível de filtrar por campo.
"""

import json
import logging
import sys
from datetime import UTC, datetime

from app.core.config import get_settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Qualquer coisa passada em `extra=` entra no JSON — é assim que se
        # correlaciona log com request_id sem concatenar string na mensagem.
        if hasattr(record, "context"):
            payload["context"] = record.context
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging() -> None:
    settings = get_settings()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())

    # uvicorn, arq e sqlalchemy instalam handlers próprios. Sem zerá-los, cada
    # linha sai duas vezes: uma no formato deles, outra em JSON pelo root.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "arq", "arq.worker", "sqlalchemy.engine"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True
