"""Compare jetro against jmespath / jsonpath-ng / glom on complex queries.

Run from the repo root after ``maturin develop --release``::

    python benches/compare.py

Each workload runs the equivalent expression in every library that
supports it; rows that say ``n/a`` mean the library does not express
the workload at all (or expressing it would require a pre/post-walk
in pure Python that defeats the comparison).

Numbers are wall-clock per iteration (microseconds). Lower = faster.
"""

import json
import statistics
import time
from collections import Counter
from typing import Any, Callable

import jetro
import jmespath
import jq as pyjq
import jsonpath_ng.ext as jpng
from glom import glom


def make_doc(n_users: int = 1000, n_orders: int = 50) -> bytes:
    """Build a representative dataset: an outer object with `users`
    (mostly active, mixed roles) and per-user `orders` arrays."""
    users = []
    for i in range(n_users):
        users.append({
            "id": i,
            "name": f"user{i}",
            "email": f"u{i}@example.com",
            "active": (i % 3) != 0,
            "score": (i * 17) % 100,
            "role": "admin" if i % 50 == 0 else ("user" if i % 5 else "guest"),
            "tags": [f"t{i % 7}", f"t{i % 11}"],
            "orders": [
                {"id": i * 1000 + k, "total": (k + 1) * 7.5, "status": "open" if k % 2 else "closed"}
                for k in range(n_orders if i % 100 == 0 else 5)
            ],
        })
    return json.dumps({"users": users, "meta": {"version": 1}}).encode()


DOC_BYTES = make_doc()
DOC_OBJ = json.loads(DOC_BYTES)


def time_it(fn: Callable[[], Any], iters: int = 200, warmup: int = 20) -> float:
    """Return median per-iteration wall-clock in microseconds."""
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(iters):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1e6)
    return statistics.median(samples)


# ── Workloads ────────────────────────────────────────────────────────

def bench_active_emails():
    """Project email of every active user."""
    j = jetro.Jetro.from_bytes(DOC_BYTES)
    eng = jetro.JetroEngine()

    def jet():
        return eng.collect(j,"$.users.filter(active).map(email)")

    jp_compiled = jmespath.compile("users[?active].email")
    def jmes():
        return jp_compiled.search(DOC_OBJ)

    jpng_compiled = jpng.parse("$.users[?(@.active)].email")
    def jp():
        return [m.value for m in jpng_compiled.find(DOC_OBJ)]

    def gl():
        return [u["email"] for u in DOC_OBJ["users"] if u["active"]]

    jq_compiled = pyjq.compile(".users | map(select(.active) | .email)")
    def jq():
        return jq_compiled.input_value(DOC_OBJ).first()

    return ("active emails", jet, jmes, jp, gl, jq)


def bench_admin_count():
    """Count users whose role is 'admin'."""
    j = jetro.Jetro.from_bytes(DOC_BYTES)
    eng = jetro.JetroEngine()

    def jet():
        return eng.collect(j,'$.users.filter(role == "admin").len()')

    jp_compiled = jmespath.compile("length(users[?role == 'admin'])")
    def jmes():
        return jp_compiled.search(DOC_OBJ)

    jpng_compiled = jpng.parse("$.users[?(@.role=='admin')]")
    def jp():
        return sum(1 for _ in jpng_compiled.find(DOC_OBJ))

    def gl():
        return sum(1 for u in DOC_OBJ["users"] if u["role"] == "admin")

    jq_compiled = pyjq.compile('.users | map(select(.role == "admin")) | length')
    def jq():
        return jq_compiled.input_value(DOC_OBJ).first()

    return ("admin count", jet, jmes, jp, gl, jq)


def bench_top_scorers():
    """Top-5 active users by score, project name+score."""
    j = jetro.Jetro.from_bytes(DOC_BYTES)
    eng = jetro.JetroEngine()

    def jet():
        return eng.collect(j,
            "$.users.filter(active).sort_by(-score).take(5).map({name, score})"
        )

    jp_compiled = jmespath.compile(
        "reverse(sort_by(users[?active], &score))[:5].{name: name, score: score}"
    )
    def jmes():
        return jp_compiled.search(DOC_OBJ)

    jpng_compiled = jpng.parse("$.users[?(@.active)]")
    def jp():
        active = [m.value for m in jpng_compiled.find(DOC_OBJ)]
        active.sort(key=lambda u: -u["score"])
        return [{"name": u["name"], "score": u["score"]} for u in active[:5]]

    def gl():
        active = [u for u in DOC_OBJ["users"] if u["active"]]
        active.sort(key=lambda u: -u["score"])
        return [{"name": u["name"], "score": u["score"]} for u in active[:5]]

    jq_compiled = pyjq.compile(
        ".users | map(select(.active)) | sort_by(-.score) | .[:5] | "
        "map({name: .name, score: .score})"
    )
    def jq():
        return jq_compiled.input_value(DOC_OBJ).first()

    return ("top scorers", jet, jmes, jp, gl, jq)


def bench_revenue_active():
    """Sum of all order totals belonging to active users."""
    j = jetro.Jetro.from_bytes(DOC_BYTES)
    eng = jetro.JetroEngine()

    def jet():
        return eng.collect(j,
            "$.users.filter(active).map(orders).flatten().map(total).sum()"
        )

    jp_compiled = jmespath.compile("sum(users[?active].orders[].total)")
    def jmes():
        return jp_compiled.search(DOC_OBJ)

    jpng_compiled = jpng.parse("$.users[?(@.active)].orders[*].total")
    def jp():
        return sum(m.value for m in jpng_compiled.find(DOC_OBJ))

    def gl():
        return sum(
            o["total"]
            for u in DOC_OBJ["users"]
            if u["active"]
            for o in u["orders"]
        )

    jq_compiled = pyjq.compile(
        "[.users[] | select(.active) | .orders[].total] | add"
    )
    def jq():
        return jq_compiled.input_value(DOC_OBJ).first()

    return ("revenue (active)", jet, jmes, jp, gl, jq)


def bench_deep_find_by_total():
    """Find every order — anywhere in the tree — with total > 100."""
    j = jetro.Jetro.from_bytes(DOC_BYTES)
    eng = jetro.JetroEngine()

    def jet():
        return eng.collect(j,"$..find(@ kind object and total > 100)")

    jp_compiled = jmespath.compile("users[].orders[?total > `100`]")
    def jmes():
        nested = jp_compiled.search(DOC_OBJ) or []
        return [o for sub in nested for o in sub]

    jpng_compiled = jpng.parse("$..*[?(@.total > 100)]")
    def jp():
        return [m.value for m in jpng_compiled.find(DOC_OBJ)]

    def gl():
        return [
            o
            for u in DOC_OBJ["users"]
            for o in u["orders"]
            if o["total"] > 100
        ]

    jq_compiled = pyjq.compile(
        "[.. | objects | select(.total != null and .total > 100)]"
    )
    def jq():
        return jq_compiled.input_value(DOC_OBJ).first()

    return ("deep total>100", jet, jmes, jp, gl, jq)


def bench_group_by_role():
    """Count users per role; produce {admin: n, user: n, guest: n}."""
    j = jetro.Jetro.from_bytes(DOC_BYTES)
    eng = jetro.JetroEngine()

    def jet():
        return eng.collect(j,"$.users.group_by(role).transform_values(len)")

    def jmes():
        # jmespath cannot group_by; the closest expression-only form
        # would need Python post-processing, defeating the comparison.
        return None

    def jp():
        return None  # jsonpath-ng has no group_by

    def gl():
        c = Counter(u["role"] for u in DOC_OBJ["users"])
        return dict(c)

    jq_compiled = pyjq.compile(
        ".users | group_by(.role) | map({(.[0].role): length}) | add"
    )
    def jq():
        return jq_compiled.input_value(DOC_OBJ).first()

    return ("group by role", jet, jmes, jp, gl, jq)


def bench_users_with_open_orders():
    """Project email of every user who has at least one open order
    with total >= 50."""
    j = jetro.Jetro.from_bytes(DOC_BYTES)
    eng = jetro.JetroEngine()

    def jet():
        return eng.collect(j,
            '$.users.filter(orders.any(status == "open" and total >= 50)).map(email)'
        )

    jp_compiled = jmespath.compile(
        "users[?length(orders[?status == 'open' && total >= `50`]) > `0`].email"
    )
    def jmes():
        return jp_compiled.search(DOC_OBJ)

    # jsonpath-ng cannot express "users where orders match X"; punt to
    # a hybrid query.
    jpng_compiled = jpng.parse("$.users[*]")
    def jp():
        out = []
        for m in jpng_compiled.find(DOC_OBJ):
            u = m.value
            if any(o["status"] == "open" and o["total"] >= 50 for o in u["orders"]):
                out.append(u["email"])
        return out

    def gl():
        return [
            u["email"]
            for u in DOC_OBJ["users"]
            if any(o["status"] == "open" and o["total"] >= 50 for o in u["orders"])
        ]

    jq_compiled = pyjq.compile(
        ".users | map(select(any(.orders[]; .status == \"open\" and .total >= 50))) | "
        "map(.email)"
    )
    def jq():
        return jq_compiled.input_value(DOC_OBJ).first()

    return ("nested any-filter", jet, jmes, jp, gl, jq)


# ── Runner ───────────────────────────────────────────────────────────

LIBS = ["jetro", "jmespath", "jsonpath-ng", "glom (py)", "pyjq"]


def run() -> None:
    print(
        f"corpus: {len(DOC_BYTES) / 1024:.1f} KB JSON, "
        f"{len(DOC_OBJ['users'])} users, ~5–50 orders each"
    )
    print(f"{'workload':<22} " + " ".join(f"{lib:>14}" for lib in LIBS))
    print("-" * 88)

    workloads = [
        bench_active_emails(),
        bench_admin_count(),
        bench_top_scorers(),
        bench_revenue_active(),
        bench_deep_find_by_total(),
        bench_group_by_role(),
        bench_users_with_open_orders(),
    ]
    for name, jet, jmes, jp, gl, jq in workloads:
        cells = []
        for fn in (jet, jmes, jp, gl, jq):
            try:
                if fn() is None:
                    cells.append("n/a")
                    continue
                t = time_it(fn)
                cells.append(f"{t:>10.1f} µs")
            except Exception as e:  # noqa: BLE001
                cells.append(f"ERR: {type(e).__name__}")
        print(f"{name:<22} " + " ".join(f"{c:>14}" for c in cells))


if __name__ == "__main__":
    run()
