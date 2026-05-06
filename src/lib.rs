//! PyO3 bindings for `jetro-core`.
//!
//! Exposes two classes — `Jetro` for single-document workloads and
//! `JetroEngine` for many-document/many-query workloads with a shared
//! plan cache. Results are converted into Python-native values
//! (`None` / `bool` / `int` / `float` / `str` / `list` / `dict`) so
//! callers never have to touch a Rust type directly.

use jetro_core::{
    EvalError as CoreEvalError, Jetro as CoreJetro, JetroEngine as CoreJetroEngine,
    JetroEngineError as CoreJetroEngineError,
};
use pyo3::create_exception;
use pyo3::exceptions::PyException;
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyBytes, PyDict, PyList, PyString};
use serde_json::Value;

create_exception!(_jetro, JetroError, PyException);
create_exception!(_jetro, JetroParseError, JetroError);
create_exception!(_jetro, JetroEvalError, JetroError);

/// Convert a `jetro-core` `EvalError` into the Python-side `JetroEvalError`.
fn map_eval_err(err: CoreEvalError) -> PyErr {
    JetroEvalError::new_err(err.to_string())
}

/// Convert a `jetro-core` engine-level error into the appropriate
/// Python exception. Parse-stage failures surface as `JetroParseError`
/// so callers can distinguish bad JSON from bad queries.
fn map_engine_err(err: CoreJetroEngineError) -> PyErr {
    match err {
        CoreJetroEngineError::Json(e) => JetroParseError::new_err(e.to_string()),
        CoreJetroEngineError::Eval(e) => JetroEvalError::new_err(e.to_string()),
    }
}

/// Walk a `serde_json::Value` and emit the equivalent Python object,
/// preferring native containers (`PyList`, `PyDict`) over JSON
/// round-tripping. Keeps the conversion overhead a single tree walk.
fn json_to_py(py: Python<'_>, value: Value) -> PyResult<PyObject> {
    Ok(match value {
        Value::Null => py.None(),
        Value::Bool(b) => PyBool::new_bound(py, b).to_owned().unbind().into_any(),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                i.into_py(py)
            } else if let Some(u) = n.as_u64() {
                u.into_py(py)
            } else if let Some(f) = n.as_f64() {
                f.into_py(py)
            } else {
                py.None()
            }
        }
        Value::String(s) => PyString::new_bound(py, &s).into_any().unbind(),
        Value::Array(items) => {
            let list = PyList::empty_bound(py);
            for item in items {
                list.append(json_to_py(py, item)?)?;
            }
            list.into_any().unbind()
        }
        Value::Object(map) => {
            let dict = PyDict::new_bound(py);
            for (k, v) in map {
                dict.set_item(k, json_to_py(py, v)?)?;
            }
            dict.into_any().unbind()
        }
    })
}

/// Single-document query handle. Construct from raw JSON bytes; reuse
/// across many queries on the same document. Holds a thread-local VM
/// internally so compile and path-resolution caches accumulate as
/// queries are issued.
#[pyclass(name = "Jetro")]
struct PyJetro {
    inner: CoreJetro,
}

#[pymethods]
impl PyJetro {
    /// Build a `Jetro` from raw JSON bytes (`bytes` / `bytearray` /
    /// `memoryview`). The bytes are not parsed eagerly when the
    /// `simd-json` feature is active in `jetro-core`; the tape is
    /// built lazily on the first query that needs it.
    #[staticmethod]
    fn from_bytes(data: &Bound<'_, PyBytes>) -> PyResult<Self> {
        let bytes = data.as_bytes().to_vec();
        let inner = CoreJetro::from_bytes(bytes).map_err(|e| JetroParseError::new_err(e.to_string()))?;
        Ok(Self { inner })
    }

    /// Build a `Jetro` from a UTF-8 JSON string.
    #[staticmethod]
    fn from_str(text: &str) -> PyResult<Self> {
        let inner = CoreJetro::from_bytes(text.as_bytes().to_vec())
            .map_err(|e| JetroParseError::new_err(e.to_string()))?;
        Ok(Self { inner })
    }

    /// Evaluate `expr` against this document and return the result as
    /// a Python-native value (`None` / `bool` / `int` / `float` /
    /// `str` / `list` / `dict`).
    ///
    /// This call holds the GIL for the duration of the query because
    /// `jetro-core::Jetro` is not `Send` (it caches lazy
    /// document state via `OnceCell`). A `Send`-safe wrapper that
    /// releases the GIL during long queries is a future enhancement.
    fn collect(&self, py: Python<'_>, expr: &str) -> PyResult<PyObject> {
        let value = self.inner.collect(expr).map_err(map_eval_err)?;
        json_to_py(py, value)
    }
}

/// Long-lived multi-document query engine. Use when the same process
/// evaluates many expressions over many documents — parse / lower /
/// compile work is amortised across calls via an explicit plan cache.
#[pyclass(name = "JetroEngine")]
struct PyJetroEngine {
    inner: CoreJetroEngine,
}

#[pymethods]
impl PyJetroEngine {
    #[new]
    fn new() -> Self {
        Self {
            inner: CoreJetroEngine::default(),
        }
    }

    /// Evaluate `expr` against an already-constructed `Jetro` document
    /// using the engine's shared plan cache.
    fn collect(&self, py: Python<'_>, document: &PyJetro, expr: &str) -> PyResult<PyObject> {
        let value = self.inner.collect(&document.inner, expr).map_err(map_eval_err)?;
        json_to_py(py, value)
    }

    /// Parse raw JSON bytes into a fresh `Jetro` and evaluate `expr`.
    /// Convenience wrapper for the common single-shot use case.
    fn collect_bytes(
        &self,
        py: Python<'_>,
        data: &Bound<'_, PyBytes>,
        expr: &str,
    ) -> PyResult<PyObject> {
        let bytes = data.as_bytes().to_vec();
        let value = self.inner.collect_bytes(bytes, expr).map_err(map_engine_err)?;
        json_to_py(py, value)
    }

    /// Discard every cached query plan. The next `collect` call
    /// recompiles from source.
    fn clear_cache(&self) {
        self.inner.clear_cache();
    }
}

/// Module entry point. Registers the two classes and the exception
/// hierarchy onto the `_jetro` extension module; the user-facing
/// re-export lives in `python/jetro/__init__.py`.
#[pymodule]
fn _jetro(py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyJetro>()?;
    m.add_class::<PyJetroEngine>()?;
    m.add("JetroError", py.get_type_bound::<JetroError>())?;
    m.add("JetroParseError", py.get_type_bound::<JetroParseError>())?;
    m.add("JetroEvalError", py.get_type_bound::<JetroEvalError>())?;
    Ok(())
}
