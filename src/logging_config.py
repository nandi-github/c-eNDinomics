# filename: logging_config.py
"""
Shared logging configuration for the eNDinomics simulator stack.

Environment variable:
  SIM_DEBUG=1   → root level DEBUG  (verbose; all simulator internals visible)
  SIM_DEBUG=0   → root level WARNING (default; clean for production / API)

Call setup_logging() once at application startup (e.g., top of api.py or cli.py).
All other modules use:

    import logging
    logger = logging.getLogger(__name__)

and emit at the appropriate level — the root config governs what actually appears.
"""

import logging
import os


def setup_logging() -> None:
    """
    Configure the root logger based on SIM_DEBUG environment variable.
    Safe to call multiple times (handlers are cleared first).
    """
    sim_debug = os.environ.get("SIM_DEBUG", "0").strip()
    level = logging.DEBUG if sim_debug == "1" else logging.WARNING

    root = logging.getLogger()
    # Clear any existing handlers (idempotent re-calls)
    root.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s",
                          datefmt="%H:%M:%S")
    )
    root.addHandler(handler)
    root.setLevel(level)

    if level == logging.DEBUG:
        logging.getLogger(__name__).debug(
            "SIM_DEBUG=1 — logging level set to DEBUG"
        )


# --- End of file ---
