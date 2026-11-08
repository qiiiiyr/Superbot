import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


class _MaskSecrets(logging.Filter):
    def __init__(self, secrets: list[str]):
        super().__init__()
        self.secrets = [s for s in secrets if s]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for s in self.secrets:
            msg = msg.replace(s, "***")
        record.msg, record.args = msg, ()
        return True


def setup_logging(log_dir: Path = Path("data/logs"), secrets: list[str] | None = None) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
        h.close()
    mask = _MaskSecrets(secrets or [])
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    for h in (
        logging.StreamHandler(),
        RotatingFileHandler(
            log_dir / "superbot.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        ),
    ):
        h.addFilter(mask)
        h.setFormatter(fmt)
        root.addHandler(h)
    root.setLevel(logging.INFO)
