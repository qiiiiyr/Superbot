import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


class _MaskSecrets(logging.Formatter):
    """Masks secrets in the final text, so tracebacks are covered too."""

    def __init__(self, secrets: list[str]):
        super().__init__("%(asctime)s %(levelname)s %(name)s: %(message)s")
        self.secrets = [s for s in secrets if s]

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        for s in self.secrets:
            text = text.replace(s, "***")
        return text


def setup_logging(log_dir: Path = Path("data/logs"), secrets: list[str] | None = None) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
        h.close()
    fmt = _MaskSecrets(secrets or [])
    for h in (
        logging.StreamHandler(),
        RotatingFileHandler(
            log_dir / "superbot.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        ),
    ):
        h.setFormatter(fmt)
        root.addHandler(h)
    root.setLevel(logging.INFO)
