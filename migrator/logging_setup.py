"""ログ。移行は**あとから何をしたか追える**ことが要るので、既定で INFO を出す。"""

from __future__ import annotations

import logging
import sys


def setup(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("migrator")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
        logger.addHandler(handler)
    return logger
