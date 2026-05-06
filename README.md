# jetro

> Query, shape, and patch JSON in one expression — at Rust speed.

Python bindings for [`jetro`](https://github.com/mitghi/jetro), a JSON
query, transform, and patch DSL. Filter, project, group, aggregate,
write back to deeply nested data, and pattern-match — all in a single
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

`jetro` outperforms every comparable Python JSON DSL on the same
queries. Numbers below are median wall-clock per iteration on a 403 KB
JSON document with 1000 users and ~5–50 orders each, plan cache warm:

| Workload | jetro | jmespath | jsonpath-ng | pyjq |
|----------|------:|---------:|------------:|-----:|
| `users.filter(active).map(email)` | **88 µs** | 540 µs | 2 890 µs | 19 200 µs |
| `users.filter(role=="admin").len()` | **37 µs** | 1 280 µs | 1 720 µs | 19 300 µs |
| top-5 active users by score | **42 µs** | 940 µs | 2 190 µs | 20 900 µs |
| sum of order totals (active users) | **293 µs** | 1 770 µs | 11 100 µs | 22 500 µs |
| `$..find(@ kind object and total > 100)` | **3 340 µs** | 7 910 µs | 76 900 µs | 87 000 µs |
| group users by role, count | **2 310 µs** | n/a | n/a | 20 600 µs |
| users with any open order ≥ 50 | **2 920 µs** | 14 700 µs | 850 µs\* | 28 200 µs |

\* jsonpath-ng's filter compiler happens to vectorise this single
  query; it is 10–100× slower than jetro on every other workload.

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
