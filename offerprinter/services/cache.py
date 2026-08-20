"""An on-disk cache for LLM responses.

Job hunting is iterative: you tweak a bullet in your CV and re-run, or you try
the same role with a different prompt. Without a cache you pay full price every
time and wait the full thirty seconds. With one, only the calls whose inputs
actually changed are re-issued.

The cache key is a hash of everything that can change the answer — provider,
model, temperature, max tokens, and both prompts — so a different model or a
reworded prompt correctly misses. Entries live in
``~/.offerprinter/cache/`` as plain JSON files you can inspect or delete.

Implemented as a decorator around any `LLMProvider`, so nothing else in the
codebase needs to know it exists.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from offerprinter.llm.base import LLMProvider
from offerprinter.services.tracker import DEFAULT_HOME

#: Entries older than this are ignored (and cleaned up opportunistically).
DEFAULT_TTL_DAYS = 30


def cache_dir() -> Path:
    home = Path(os.environ.get("OFFERPRINTER_HOME") or DEFAULT_HOME)
    return home / "cache"


class ResponseCache:
    """Content-addressed storage for completions."""

    def __init__(self, directory: Path | None = None, ttl_days: int = DEFAULT_TTL_DAYS) -> None:
        self.directory = directory or cache_dir()
        self.ttl_seconds = ttl_days * 86400
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(provider: str, model: str, system: str, user: str, extra: str = "") -> str:
        digest = hashlib.sha256()
        for part in (provider, model, system, user, extra):
            digest.update(part.encode("utf-8"))
            digest.update(b"\x00")  # separator, so fields can't run together
        return digest.hexdigest()

    def _path(self, key: str) -> Path:
        # Shard by the first two characters so the directory stays browsable.
        return self.directory / key[:2] / f"{key}.json"

    def get(self, key: str) -> str | None:
        path = self._path(key)
        if not path.is_file():
            self.misses += 1
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self.misses += 1
            return None

        if time.time() - payload.get("stored_at", 0) > self.ttl_seconds:
            path.unlink(missing_ok=True)
            self.misses += 1
            return None

        self.hits += 1
        return payload.get("response")

    def put(self, key: str, response: str, meta: dict | None = None) -> None:
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {"stored_at": time.time(), "response": response, "meta": meta or {}},
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass  # a cache that cannot write is a slow cache, not a broken run

    # -- maintenance --------------------------------------------------------

    def stats(self) -> tuple[int, int]:
        """Return (number of entries, total bytes)."""
        if not self.directory.is_dir():
            return (0, 0)
        files = list(self.directory.rglob("*.json"))
        return (len(files), sum(f.stat().st_size for f in files))

    def clear(self) -> int:
        """Delete every entry. Returns how many were removed."""
        if not self.directory.is_dir():
            return 0
        removed = 0
        for path in self.directory.rglob("*.json"):
            path.unlink(missing_ok=True)
            removed += 1
        return removed


class CachedProvider(LLMProvider):
    """Wraps a provider so identical calls are served from disk.

    Token usage is only recorded on a miss, which is the honest thing to do:
    a cached answer really did cost nothing this time.
    """

    def __init__(self, inner: LLMProvider, cache: ResponseCache | None = None) -> None:
        # Deliberately not calling super().__init__: we delegate state to `inner`
        # so that usage accounting stays on a single object.
        self.inner = inner
        self.cache = cache or ResponseCache()
        self.config = inner.config
        self.model = inner.model
        self.price_overrides = inner.price_overrides

    @property
    def usage(self):  # noqa: ANN201 - mirrors the wrapped provider
        return self.inner.usage

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def requires_key(self) -> bool:  # type: ignore[override]
        return self.inner.requires_key

    def complete(self, system: str, user: str) -> str:
        extra = f"{self.config.temperature}|{self.config.max_tokens}"
        key = ResponseCache.key(self.inner.name, self.inner.model, system, user, extra)

        cached = self.cache.get(key)
        if cached is not None:
            return cached

        response = self.inner.complete(system, user)
        self.cache.put(key, response, meta={"provider": self.inner.name, "model": self.model})
        return response
