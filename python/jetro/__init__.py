"""jetro — query, shape, and patch JSON in one expression.

The compiled Rust extension lives in :mod:`jetro._jetro`; this module
re-exports the names users actually want so callers can write
``from jetro import Jetro`` without reaching into the private module.
"""

from ._jetro import (
    Jetro,
    JetroEngine,
    JetroError,
    JetroParseError,
    JetroEvalError,
)

__all__ = [
    "Jetro",
    "JetroEngine",
    "JetroError",
    "JetroParseError",
    "JetroEvalError",
]
