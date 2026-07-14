mod alphabet;
mod expressions;

use pyo3::prelude::*;
use pyo3::types::PyModule;

#[pymodule]
fn _internal(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
