import logging
import sys
from pythonjsonlogger import jsonlogger


def setup_json_logging(service: str, level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s %(tenant_id)s %(path)s %(method)s %(status_code)s %(duration_ms)s %(extra)s"
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    root = logging.LoggerAdapter(root, {"service": service})
