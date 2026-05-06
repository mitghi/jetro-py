"""Type stubs for the jetro Python bindings.

Mirrors the surface exposed by :mod:`jetro._jetro` so editors,
``mypy``, and ``pyright`` can reason about return types and argument
shapes without having to introspect the compiled extension.
"""

from typing import Any, Union

class JetroError(Exception):
    """Base class for every error raised by the jetro engine."""

class JetroParseError(JetroError):
    """Raised when JSON input cannot be parsed."""

class JetroEvalError(JetroError):
    """Raised when an otherwise-valid query fails at runtime."""

class Jetro:
    """A single JSON document handle. Reusable across many queries."""

    @staticmethod
    def from_bytes(data: Union[bytes, bytearray, memoryview]) -> "Jetro": ...
    @staticmethod
    def from_str(text: str) -> "Jetro": ...
    def collect(self, expr: str) -> Any: ...

class JetroEngine:
    """Multi-document query engine with a shared plan cache."""

    def __init__(self) -> None: ...
    def collect(self, document: Jetro, expr: str) -> Any: ...
    def collect_bytes(
        self,
        data: Union[bytes, bytearray, memoryview],
        expr: str,
    ) -> Any: ...
    def clear_cache(self) -> None: ...
