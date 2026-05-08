# jetro

> Query, shape, and patch JSON in one expression — at Rust speed.

Python bindings for [`jetro`](https://github.com/mitghi/jetro), a JSON
query, transform, and patch DSL. Filter, project, group, aggregate,
write back to deeply nested data, and pattern-match, all in a single
expression. Streaming with demand propagation, structural bitmap index
for deep search, and a complete patch surface (`.set` / `.modify` /
`.delete`).

## Install

```
pip install jetro
```

Wheels are published for CPython 3.9+ on linux (x86_64, aarch64),
macOS (universal2), and windows (x86_64). Building from source
requires a Rust toolchain.

## Learn

The [jetro book](https://mitghi.github.io/jetro-book/) is the best
place to start. It includes examples and valuable details throughout.

## Quickstart

```python
from jetro import Jetro, JetroEngine

j = Jetro.from_str('{"books":[{"title":"a","price":12},{"title":"b","price":7}]}')

j.collect("$.books.len()")                          # 2
j.collect("$.books.filter(price > 10).map(title)")  # ["a"]
j.collect("$.books.map(price).sum()")               # 19
```

`JetroEngine` amortises parsing and planning across many queries:

```python
eng = JetroEngine()
for doc in stream_of_jsons:
    payload = eng.collect_bytes(doc, "$.users.filter(active).map(email)")
    ...
```

## Pattern matching

```python
j = Jetro.from_str('{"u": {"role": "admin", "id": 9}}')

j.collect("""
    match $.u with {
        {role: "admin", id: i} -> {tag: "a", n: i},
        {role: "user",  id: i} -> {tag: "u", n: i},
        _                      -> {tag: "x"}
    }
""")
# {"tag": "a", "n": 9}
```

Deep search:

```python
j.collect("""
    $..match {
        {tag: "click", id: i} -> i,
        _                     -> false
    }
""")
```

## Performance

`jetro` outperforms several comparable Python JSON DSL on the same
queries, and matches or beats hand-rolled Python on compound
workloads. Numbers below are median wall-clock per iteration on a
403 KB JSON document with 1000 users and ~5–50 orders each. Each
library is queried in its own idiomatic single expression for the
same semantic workload.

### Warm path (cached parse + cached plan)

The document is parsed once; subsequent queries hit `JetroEngine`'s
plan cache. Mirrors a long-running process answering many queries
against the same document.

| Workload | jetro | jmespath | jsonpath-ng | pyjq | glom (py) |
|----------|------:|---------:|------------:|-----:|----------:|
| `users.filter(active).map(email)` | **86 µs** | 537 µs | 2 899 µs | 18 829 µs | 32 µs |
| `users.filter(role=="admin").len()` | **37 µs** | 1 237 µs | 1 682 µs | 18 951 µs | 29 µs |
| top-5 active users by score | **43 µs** | 931 µs | 2 165 µs | 20 643 µs | 84 µs |
| sum of order totals (active users) | **129 µs** | 1 704 µs | 11 051 µs | 22 290 µs | 177 µs |
| orders with `total > 100` | **498 µs** | 7 798 µs | 11 219 µs | 24 624 µs | 221 µs |
| group users by role, count | **73 µs** | n/a | n/a | 20 610 µs | 68 µs |
| users with any open order ≥ 50 | **2 601 µs** | 14 642 µs | 816 µs\* | 28 032 µs | 379 µs |

The `glom (py)` column is hand-written Python list / generator
expressions over an already-parsed `dict`, included as a "no DSL,
maximum-speed Python" reference.

### Cold path (parse + query per iteration)

Every iteration re-parses the raw bytes, then runs the query. Mirrors
the typical web-server pattern of "receive JSON request, run query,
return result" where parse cost dominates. jetro's [simd-json](https://github.com/simd-lite/simd-json)
bytes→tape parser is several times faster than `json.loads`, so the
gap to several other library widens substantially.

| Workload | jetro | jmespath | jsonpath-ng | pyjq | glom (py) |
|----------|------:|---------:|------------:|-----:|----------:|
| `users.filter(active).map(email)` | **574 µs** | 3 828 µs | 15 984 µs | 23 526 µs | 3 340 µs |
| top-5 active users by score | **538 µs** | 4 214 µs | 15 016 µs | 25 131 µs | 3 405 µs |
| group users by role, count | **547 µs** | n/a | n/a | 25 037 µs | 3 339 µs |

In the cold path jetro is **~6× faster than hand-rolled Python** and
**7–46× faster than every other DSL** because parse cost dominates
and [simd-json](https://github.com/simd-lite/simd-json) beats `json.loads` by a wide margin.

Reproduce with:

```
pip install -r benches/requirements.txt
python benches/compare.py
```

## Errors

```python
from jetro import JetroParseError, JetroEvalError
```

`JetroParseError` covers JSON parse failures; `JetroEvalError` covers
runtime query errors. Both subclass `JetroError`.

## API

| Class | Method | Notes |
|-------|--------|-------|
| `Jetro` | `from_bytes(data) -> Jetro` | accepts `bytes` / `bytearray` / `memoryview` |
| `Jetro` | `from_str(text) -> Jetro` | accepts `str` |
| `Jetro` | `collect(expr) -> Any` | evaluates against this document |
| `JetroEngine` | `collect(doc, expr) -> Any` | reuses cached plan |
| `JetroEngine` | `collect_bytes(data, expr) -> Any` | parses + queries in one call |
| `JetroEngine` | `clear_cache()` | drops cached plans |

## Language reference

See the upstream [`SYNTAX.md`](https://github.com/mitghi/jetro/blob/main/jetro-core/src/SYNTAX.md)
for the full language surface.

## Building from source

```
maturin develop --release
pytest
```

## License

MIT.
