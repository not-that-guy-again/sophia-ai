"""Load the Sophia Constitution from disk.

The constitution defines Sophia's identity, voice, ethics, and behavioral
patterns.  It is loaded once at startup and injected into user-facing LLM
calls via the prompt assembler.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path(__file__).parent.parent / "constitution.md"


def load_constitution(path: str | None = None) -> str:
    """Load the Sophia Constitution from disk.

    Args:
        path: Filesystem path to the constitution file.  Defaults to
              ``sophia/constitution.md`` relative to the package root.

    Returns:
        The full text of the constitution, or an empty string if the file
        does not exist.  Sophia functions without a constitution but lacks
        a consistent personality.
    """
    target = Path(path) if path is not None else _DEFAULT_PATH

    if not target.exists():
        logger.warning("Constitution file not found at %s — running without identity layer", target)
        return ""

    return target.read_text(encoding="utf-8")
