use pyo3::prelude::*;

pub mod agentx;
pub mod oid;
pub mod types;

#[pymodule(name = "core")]
fn snmpkit_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_class::<oid::Oid>()?;
    m.add_class::<types::Value>()?;
    m.add_class::<agentx::pdu::VarBind>()?;

    // AgentX protocol bindings
    m.add_class::<agentx::bindings::AgentXHeader>()?;
    m.add_class::<agentx::bindings::AgentXResponse>()?;
    m.add_class::<agentx::bindings::AgentXGet>()?;
    m.add_class::<agentx::bindings::AgentXGetBulk>()?;
    m.add_class::<agentx::bindings::AgentXTestSet>()?;
    m.add_class::<agentx::bindings::PduTypes>()?;
    m.add_class::<agentx::bindings::CloseReasons>()?;
    m.add_class::<agentx::bindings::ResponseErrors>()?;

    m.add_function(pyo3::wrap_pyfunction!(
        agentx::bindings::encode_open_pdu,
        m
    )?)?;
    m.add_function(pyo3::wrap_pyfunction!(
        agentx::bindings::encode_close_pdu,
        m
    )?)?;
    m.add_function(pyo3::wrap_pyfunction!(
        agentx::bindings::encode_register_pdu,
        m
    )?)?;
    m.add_function(pyo3::wrap_pyfunction!(
        agentx::bindings::encode_unregister_pdu,
        m
    )?)?;
    m.add_function(pyo3::wrap_pyfunction!(
        agentx::bindings::encode_response_pdu,
        m
    )?)?;
    m.add_function(pyo3::wrap_pyfunction!(
        agentx::bindings::encode_notify_pdu,
        m
    )?)?;
    m.add_function(pyo3::wrap_pyfunction!(
        agentx::bindings::encode_ping_pdu,
        m
    )?)?;
    m.add_function(pyo3::wrap_pyfunction!(agentx::bindings::decode_header, m)?)?;
    m.add_function(pyo3::wrap_pyfunction!(
        agentx::bindings::decode_response_pdu,
        m
    )?)?;
    m.add_function(pyo3::wrap_pyfunction!(agentx::bindings::decode_get_pdu, m)?)?;
    m.add_function(pyo3::wrap_pyfunction!(
        agentx::bindings::decode_getbulk_pdu,
        m
    )?)?;
    m.add_function(pyo3::wrap_pyfunction!(
        agentx::bindings::decode_testset_pdu,
        m
    )?)?;

    m.add("HEADER_SIZE", agentx::bindings::HEADER_SIZE_PY)?;

    Ok(())
}

#[cfg(test)]
mod tests {
    #[test]
    fn test_version() {
        assert_eq!(env!("CARGO_PKG_VERSION"), "0.1.0");
    }
}
