"""召回性能基准：对比索引缓存前后的耗时。

用法:
    PYTHONPATH=src python tests/bench_recall.py

生成 N 条不重复记忆，对每条做 M 次召回，打印平均耗时。
纯本地标准库，不写网络，不污染真实数据库（用临时目录）。
"""

from __future__ import annotations

import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from portable_memory.config import Config  # noqa: E402
from portable_memory.db import Store  # noqa: E402
from portable_memory.pipeline import Retriever  # noqa: E402

SIZES = (100, 500, 2000)
QUERIES = 20
NS = "bench"


def make_store(tmp: Path) -> Store:
    return Store(tmp / "bench.sqlite3")


def make_config(tmp: Path) -> Config:
    return Config(
        data_dir=tmp,
        db_path=tmp / "bench.sqlite3",
        host="127.0.0.1", port=0, token="",
        decay_half_life_days=30.0, default_limit=8, max_limit=50,
    )


def seed(store: Store, n: int) -> None:
    for i in range(n):
        store.add(
            f"第{i}条：分页默认 10 条，搜索走后端参数，踩坑记录 {i}",
            tags=["分页", f"tag{i % 10}"],
            namespace=NS,
            source="bench",
        )


def bench(n: int) -> tuple[float, float]:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        store = make_store(tmp)
        config = make_config(tmp)
        seed(store, n)
        r = Retriever(store, config)

        # warm up（让首次缓存/解释器等一次性开销不计入）
        r.recall("分页", namespace=NS, limit=8)

        times: list[float] = []
        for i in range(QUERIES):
            t0 = time.perf_counter()
            r.recall(f"分页 后端参数 {i % 10}", namespace=NS, limit=8)
            times.append((time.perf_counter() - t0) * 1000)

        store.close()
        return statistics.mean(times), statistics.median(times)


def main() -> None:
    print(f"{'记忆数':>8} {'平均(ms)':>12} {'中位(ms)':>12}")
    print("-" * 34)
    for n in SIZES:
        avg, med = bench(n)
        print(f"{n:>8} {avg:>12.3f} {med:>12.3f}")


if __name__ == "__main__":
    main()
