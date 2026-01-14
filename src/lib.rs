use pyo3::prelude::*;

mod agentx;
pub mod oid;
pub mod types;

#[pymodule(name = "_core")]
fn snmpkit_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    #[test]
    fn test_version() {
        assert_eq!(env!("CARGO_PKG_VERSION"), "0.1.0");
    }
}
