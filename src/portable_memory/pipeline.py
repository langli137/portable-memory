"""Capture -> process -> recall pipeline.

Design choices (all dependency-free, Python stdlib only):
  * Tokenizer handles both CJK (bigrams) and Latin words, so Chinese queries
    such as "分页 口径" match Chinese memories without an embedding model.
  * BM25 ranks lexical relevance; time decay and access frequency keep stale
    memories from dominating. No LLM call in the hot path.
  * Everything is explainable: recall returns score components so the caller
    can see why a memory surfaced.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from typing import Iterable

from .config import Config
from .db import Memory, Store

_CJK = re.compile(r"[\u4e00-\u9fff]")
_WORD = re.compile(r"[a-z0-9_]+")


def tokenize(text: str) -> list[str]:
    """Lowercase, split Latin words, and emit CJK unigrams + bigrams."""
    text = text.lower().replace("\u3000", " ")
    tokens: list[str] = _WORD.findall(text)
    cjk_runs = re.findall(r"[\u4e00-\u9fff]+", text)
    for run in cjk_runs:
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


@dataclass
class Scored:
    memory: Memory
    score: float
    bm25: float
    recency: float
    frequency: float
    matched_terms: list[str]

    def to_dict(self) -> dict:
        d = self.memory.to_dict()
        d.update(
            score=round(self.score, 4),
            bm25=round(self.bm25, 4),
            recency=round(self.recency, 4),
            frequency=round(self.frequency, 4),
            matched_terms=self.matched_terms,
        )
        return d


@dataclass
class _Index:
    """Cached tokenized corpus + BM25 statistics for one namespace.

    Rebuilt only when the underlying memories change. All data is derived
    from real stored content — the cache stores no fabricated values.
    """

    fingerprint: tuple[int, int, float]
    tokens: dict[int, list[str]]
    df: dict[str, int]
    avgdl: float
    count: int


class Retriever:
    def __init__(self, store: Store, config: Config):
        self.store = store
        self.config = config
        # namespace -> cached index. Process-local; rebuilt automatically on
        # restart, invalidated by data fingerprint on every write.
        self._index: dict[str, _Index] = {}

    @staticmethod
    def _fingerprint(corpus: list[Memory]) -> tuple[int, int, float]:
        """Detect content changes without scanning memory text.

        - count: catches add / soft-delete
        - max id: catches id reuse edge cases
        - sum(updated_at): catches edit (content/tags/type changes)

        `touch()` only changes access_count / last_accessed, so a read does
        NOT invalidate the index — that is the whole point of the cache.
        """
        return (
            len(corpus),
            max((m.id for m in corpus), default=0),
            round(sum(m.updated_at for m in corpus), 3),
        )

    def _get_index(self, namespace: str, corpus: list[Memory]) -> _Index:
        fp = self._fingerprint(corpus)
        cached = self._index.get(namespace)
        if cached is not None and cached.fingerprint == fp:
            return cached

        # Build token index once per corpus version.
        tokens: dict[int, list[str]] = {}
        df: dict[str, int] = {}
        total_len = 0
        for m in corpus:
            d = tokenize(m.content + " " + " ".join(m.tags))
            tokens[m.id] = d
            total_len += len(d)
            for t in set(d):
                df[t] = df.get(t, 0) + 1
        index = _Index(
            fingerprint=fp,
            tokens=tokens,
            df=df,
            avgdl=(total_len / len(corpus)) if corpus else 1.0,
            count=len(corpus),
        )
        self._index[namespace] = index
        return index

    def invalidate(self, namespace: str | None = None) -> None:
        """Drop cached index(es) after a write. Safe to call redundantly."""
        if namespace is None:
            self._index.clear()
        else:
            self._index.pop(namespace, None)

    def recall(
        self,
        query: str,
        *,
        namespace: str | None = None,
        limit: int | None = None,
        memory_type: str | None = None,
        since: float | None = None,
        until: float | None = None,
    ) -> list[Scored]:
        limit = min(limit or self.config.default_limit, self.config.max_limit)
        corpus = self.store.all(namespace)
        if memory_type:
            corpus = [m for m in corpus if m.memory_type == memory_type]
        if since is not None:
            corpus = [m for m in corpus if m.created_at >= since]
        if until is not None:
            corpus = [m for m in corpus if m.created_at <= until]
        if not corpus or not query.strip():
            top = sorted(corpus, key=lambda m: (m.importance, m.access_count), reverse=True)
            return [self._score(m, 0.0, query) for m in top[:limit]]

        q_tokens = tokenize(query)
        # Tokenize is the hot path. Read per-memory tokens from the cache;
        # BM25 statistics (df/avgdl) are cached only for the unfiltered case,
        # since filters change the effective corpus.
        index = self._get_index(namespace or "", corpus)
        docs = [index.tokens[m.id] for m in corpus]
        n = len(docs)
        if memory_type is None and since is None and until is None:
            df = index.df
            avgdl = index.avgdl
        else:
            avgdl = sum(len(d) for d in docs) / n or 1.0
            df = {}
            for d in docs:
                for t in set(d):
                    df[t] = df.get(t, 0) + 1
        k1, b = 1.5, 0.75

        results: list[Scored] = []
        for m, d in zip(corpus, docs):
            tf: dict[str, int] = {}
            for t in d:
                tf[t] = tf.get(t, 0) + 1
            bm25 = 0.0
            for t in q_tokens:
                if t not in tf:
                    continue
                freq = df.get(t, 0)
                idf = math.log(1.0 + (n - freq + 0.5) / (freq + 0.5))
                denom = tf[t] + k1 * (1 - b + b * len(d) / avgdl)
                bm25 += idf * (tf[t] * (k1 + 1)) / denom
            results.append(self._score(m, bm25, query, doc_tokens=d))

        results.sort(key=lambda s: s.score, reverse=True)
        top = results[:limit]
        self.store.touch_many([s.memory.id for s in top])
        return top

    @staticmethod
    def _matched_terms(query: str, doc_tokens: set[str] | None = None) -> list[str]:
        """Query tokens actually present in the memory, in query order, de-duplicated.

        Used by the UI to explain *why* a memory surfaced. Purely derived from
        the same tokenizer as BM25 — no extra index, no fabricated data.
        When doc_tokens is supplied the caller reuses the cached tokenization.
        """
        if not query.strip():
            return []
        doc_set = set(doc_tokens) if doc_tokens is not None else set()
        seen: set[str] = set()
        matched: list[str] = []
        for t in tokenize(query):
            if t in doc_set and t not in seen:
                seen.add(t)
                matched.append(t)
        return matched

    def _score(self, m: Memory, bm25: float, query: str, doc_tokens: list[str] | None = None) -> Scored:
        age_days = max(0.0, (time.time() - m.created_at) / 86400.0)
        half = max(self.config.decay_half_life_days, 0.1)
        recency = 0.5 ** (age_days / half)
        frequency = math.log1p(max(m.access_count, 0))
        # Keep lexical signal dominant; recency/frequency are tie-breakers.
        score = bm25 * 1.0 + recency * 0.15 + frequency * 0.05 + m.importance * 0.1
        return Scored(
            memory=m,
            score=score,
            bm25=bm25,
            recency=recency,
            frequency=frequency,
            matched_terms=self._matched_terms(query, doc_tokens),
        )


def capture(
    store: Store,
    text: str,
    *,
    memory_type: str = "fact",
    namespace: str = "default",
    source: str = "",
    tags: Iterable[str] = (),
    importance: float = 1.0,
) -> tuple[Memory | None, str]:
    """Capture one observation into memory with dedup and redaction."""
    if not text or not text.strip():
        raise ValueError("empty observation")
    return store.add(
        text.strip(),
        memory_type=memory_type,
        namespace=namespace,
        source=source,
        tags=tags,
        importance=importance,
    )


def seed_from_markdown(store: Store, path, namespace: str = "default") -> dict:
    """Load a seed memory template. Sections use `##` headings; bullets become
    individual memories so each fact can be recalled and scored separately.
    """
    from pathlib import Path

    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    added = 0
    duplicates = 0
    current_type = "fact"
    bullets: list[str] = []

    def flush() -> None:
        nonlocal added, duplicates
        for b in bullets:
            _, status = store.add(b, memory_type=current_type, namespace=namespace,
                                  source="seed", tags=["seed"])
            if status == "duplicate":
                duplicates += 1
            else:
                added += 1

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            flush()
            bullets.clear()
            if "偏好" in stripped or "preference" in stripped.lower():
                current_type = "preference"
            elif "原则" in stripped or "规则" in stripped or "rule" in stripped.lower():
                current_type = "rule"
            elif "环境" in stripped or "environment" in stripped.lower():
                current_type = "environment"
            else:
                current_type = "fact"
        elif stripped.startswith("- "):
            bullets.append(stripped[2:].replace("**", "").strip())
    flush()
    return {"added": added, "duplicates": duplicates}
