import logging


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging():
    root_logger = logging.getLogger()

    if root_logger.handlers:
        return

    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
    )


def format_log_event(event: str, **fields) -> str:
    parts = [f"event={event}"]

    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={value}")

    return " ".join(parts)
