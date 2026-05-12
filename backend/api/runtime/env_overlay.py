from __future__ import annotations

import os
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager


_RUNTIME_ENV_OVERLAY_LOCK = threading.Lock()


@contextmanager
def runtime_env_overlay(values: Mapping[str, str]) -> Iterator[None]:
    with _RUNTIME_ENV_OVERLAY_LOCK:
        previous: dict[str, str | None] = {key: os.environ.get(key) for key in values}
        try:
            for key, value in values.items():
                os.environ[key] = value
            yield
        finally:
            for key, old_value in previous.items():
                if old_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old_value
