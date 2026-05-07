"""Smoke tests for the jetro Python bindings.

Run with ``pytest`` after building the extension via ``maturin develop``.
"""

import pytest
from jetro import (
    Jetro,
    JetroEngine,
    JetroEvalError,
    JetroParseError,
)


DOC = b'{"books":[{"title":"a","price":12},{"title":"b","price":7}]}'


def test_jetro_from_bytes_collects_native_types() -> None:
    j = Jetro.from_bytes(DOC)
    assert j.collect("$.books.len()") == 2
    assert j.collect("$.books.map(title)") == ["a", "b"]
    assert j.collect("$.books.filter(price > 10).map(title)") == ["a"]


def test_jetro_from_str_round_trip() -> None:
    j = Jetro.from_str('{"x": 1, "y": [true, null, "z"]}')
    # Field-access paths return the match collection (jetro wraps a
    # scalar leaf in a singleton array; an array leaf passes through).
    assert j.collect("$.x") == [1]
    assert j.collect("$.y") == [True, None, "z"]
    # Use a method call or `.first()` to unwrap to a scalar.
    assert j.collect("$.x.first()") == 1


def test_engine_amortises_plan_cache() -> None:
    eng = JetroEngine()
    j = Jetro.from_bytes(DOC)
    for _ in range(3):
        assert eng.collect(j, "$.books.map(price).sum()") == 19


def test_engine_collect_bytes_one_shot() -> None:
    eng = JetroEngine()
    out = eng.collect_bytes(DOC, "$.books.map(title)")
    assert out == ["a", "b"]


def test_pattern_match_in_python() -> None:
    j = Jetro.from_str('{"u": {"role": "admin", "id": 9}}')
    out = j.collect(
        "match $.u with { "
        "{role: \"admin\", id: i} -> {tag: \"a\", n: i}, "
        "{role: \"user\", id: i}  -> {tag: \"u\", n: i}, "
        "_                        -> {tag: \"x\"} "
        "}"
    )
    assert out == {"tag": "a", "n": 9}


def test_invalid_json_raises_parse_error() -> None:
    # JSON parse is lazy under the simd-json feature: `from_str` only
    # validates the bytes when a query forces tape construction. The
    # parse error therefore surfaces on the first `collect` call, not
    # at the constructor.
    j = Jetro.from_str("{not valid json")
    with pytest.raises((JetroParseError, JetroEvalError)):
        j.collect("$")


def test_invalid_query_raises_eval_error() -> None:
    j = Jetro.from_bytes(DOC)
    with pytest.raises(JetroEvalError):
        j.collect("totally not a query")
