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


class Retriever:
    def __init__(self, store: Store, config: Config):
        self.store = store
        self.config = config

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
        docs = [tokenize(m.content + " " + " ".join(m.tags)) for m in corpus]
        n = len(docs)
        avgdl = sum(len(d) for d in docs) / n or 1.0
        df: dict[str, int] = {}
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
            results.append(self._score(m, bm25, query))

        results.sort(key=lambda s: s.score, reverse=True)
        top = results[:limit]
        for s in top:
            self.store.touch(s.memory.id)
        return top

    @staticmethod
    def _matched_terms(m: Memory, query: str) -> list[str]:
        """Query tokens actually present in the memory, in query order, de-duplicated.

        Used by the UI to explain *why* a memory surfaced. Purely derived from
        the same tokenizer as BM25 — no extra index, no fabricated data.
        """
        if not query.strip():
            return []
        doc_tokens = set(tokenize(m.content + " " + " ".join(m.tags)))
        seen: set[str] = set()
        matched: list[str] = []
        for t in tokenize(query):
            if t in doc_tokens and t not in seen:
                seen.add(t)
                matched.append(t)
        return matched

    def _score(self, m: Memory, bm25: float, query: str) -> Scored:
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
            matched_terms=self._matched_terms(m, query),
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
