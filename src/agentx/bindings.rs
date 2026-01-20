use pyo3::prelude::*;
use pyo3::types::PyBytes;
use std::io::Cursor;

use crate::oid::Oid;

use super::bodies::{
    ClosePdu, CloseReason, GetBulkPdu, GetPdu, NotifyPdu, OpenPdu, PingPdu, RegisterPdu,
    ResponseError, ResponsePdu, TestSetPdu, UnregisterPdu,
};
use super::header::{Flags, HEADER_SIZE, Header, PduType};
use super::pdu::VarBind;

fn encode_full_pdu(header: Header, body: &[u8]) -> Vec<u8> {
    let header = header.with_payload_length(body.len() as u32);
    let mut buf = Vec::with_capacity(HEADER_SIZE + body.len());
    header.encode(&mut buf).unwrap();
    buf.extend_from_slice(body);
    buf
}

#[pyclass]
#[derive(Debug, Clone)]
pub struct AgentXHeader {
    #[pyo3(get)]
    pub pdu_type: u8,
    #[pyo3(get)]
    pub flags: u8,
    #[pyo3(get)]
    pub session_id: u32,
    #[pyo3(get)]
    pub transaction_id: u32,
    #[pyo3(get)]
    pub packet_id: u32,
    #[pyo3(get)]
    pub payload_length: u32,
}

#[pymethods]
impl AgentXHeader {
    fn __repr__(&self) -> String {
        format!(
            "AgentXHeader(type={}, session={}, transaction={}, packet={}, payload={})",
            self.pdu_type,
            self.session_id,
            self.transaction_id,
            self.packet_id,
            self.payload_length
        )
    }
}

#[pyclass]
#[derive(Debug, Clone)]
pub struct AgentXResponse {
    #[pyo3(get)]
    pub sys_uptime: u32,
    #[pyo3(get)]
    pub error: u16,
    #[pyo3(get)]
    pub index: u16,
    #[pyo3(get)]
    pub varbinds: Vec<VarBind>,
}

#[pymethods]
impl AgentXResponse {
    fn __repr__(&self) -> String {
        format!(
            "AgentXResponse(uptime={}, error={}, index={}, varbinds={})",
            self.sys_uptime,
            self.error,
            self.index,
            self.varbinds.len()
        )
    }

    #[getter]
    fn is_error(&self) -> bool {
        self.error != 0
    }
}

#[pyclass]
#[derive(Debug, Clone)]
pub struct AgentXGet {
    #[pyo3(get)]
    pub ranges: Vec<(Oid, Oid, bool)>,
}

#[pymethods]
impl AgentXGet {
    fn __repr__(&self) -> String {
        format!("AgentXGet(ranges={})", self.ranges.len())
    }
}

#[pyclass]
#[derive(Debug, Clone)]
pub struct AgentXGetBulk {
    #[pyo3(get)]
    pub non_repeaters: u16,
    #[pyo3(get)]
    pub max_repetitions: u16,
    #[pyo3(get)]
    pub ranges: Vec<(Oid, Oid, bool)>,
}

#[pyclass]
#[derive(Debug, Clone)]
pub struct AgentXTestSet {
    #[pyo3(get)]
    pub varbinds: Vec<VarBind>,
}

// Encoding functions

#[pyfunction]
pub fn encode_open_pdu(
    py: Python<'_>,
    session_id: u32,
    transaction_id: u32,
    packet_id: u32,
    timeout: u8,
    oid: &Oid,
    description: &str,
) -> PyResult<Py<PyBytes>> {
    let pdu = OpenPdu::new(timeout, oid.clone(), description.as_bytes().to_vec());
    let mut body = Vec::new();
    pdu.encode(&mut body)
        .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;

    let header = Header::new(PduType::Open, session_id, transaction_id, packet_id);
    let buf = encode_full_pdu(header, &body);
    Ok(PyBytes::new(py, &buf).into())
}

#[pyfunction]
pub fn encode_close_pdu(
    py: Python<'_>,
    session_id: u32,
    transaction_id: u32,
    packet_id: u32,
    reason: u8,
) -> PyResult<Py<PyBytes>> {
    let reason = match reason {
        1 => CloseReason::Other,
        2 => CloseReason::ParseError,
        3 => CloseReason::ProtocolError,
        4 => CloseReason::Timeouts,
        5 => CloseReason::Shutdown,
        6 => CloseReason::ByManager,
        _ => CloseReason::Other,
    };
    let pdu = ClosePdu::new(reason);
    let mut body = Vec::new();
    pdu.encode(&mut body)
        .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;

    let header = Header::new(PduType::Close, session_id, transaction_id, packet_id);
    let buf = encode_full_pdu(header, &body);
    Ok(PyBytes::new(py, &buf).into())
}

#[pyfunction]
#[pyo3(signature = (session_id, transaction_id, packet_id, subtree, priority, timeout, context=None))]
#[allow(clippy::too_many_arguments)]
pub fn encode_register_pdu(
    py: Python<'_>,
    session_id: u32,
    transaction_id: u32,
    packet_id: u32,
    subtree: &Oid,
    priority: u8,
    timeout: u8,
    context: Option<&str>,
) -> PyResult<Py<PyBytes>> {
    let pdu = RegisterPdu::new(subtree.clone(), priority, timeout);
    let mut body = Vec::new();

    if let Some(ctx) = context {
        super::pdu::encode_octet_string(&mut body, ctx.as_bytes())
            .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;
    }

    pdu.encode(&mut body)
        .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;

    let mut flags = Flags::NETWORK_BYTE_ORDER;
    if context.is_some() {
        flags |= Flags::NON_DEFAULT_CONTEXT;
    }

    let header =
        Header::new(PduType::Register, session_id, transaction_id, packet_id).with_flags(flags);
    let buf = encode_full_pdu(header, &body);
    Ok(PyBytes::new(py, &buf).into())
}

#[pyfunction]
#[pyo3(signature = (session_id, transaction_id, packet_id, subtree, priority, context=None))]
pub fn encode_unregister_pdu(
    py: Python<'_>,
    session_id: u32,
    transaction_id: u32,
    packet_id: u32,
    subtree: &Oid,
    priority: u8,
    context: Option<&str>,
) -> PyResult<Py<PyBytes>> {
    let pdu = UnregisterPdu::new(subtree.clone(), priority);
    let mut body = Vec::new();

    if let Some(ctx) = context {
        super::pdu::encode_octet_string(&mut body, ctx.as_bytes())
            .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;
    }

    pdu.encode(&mut body)
        .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;

    let mut flags = Flags::NETWORK_BYTE_ORDER;
    if context.is_some() {
        flags |= Flags::NON_DEFAULT_CONTEXT;
    }

    let header =
        Header::new(PduType::Unregister, session_id, transaction_id, packet_id).with_flags(flags);
    let buf = encode_full_pdu(header, &body);
    Ok(PyBytes::new(py, &buf).into())
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn encode_response_pdu(
    py: Python<'_>,
    session_id: u32,
    transaction_id: u32,
    packet_id: u32,
    sys_uptime: u32,
    error: u16,
    index: u16,
    varbinds: Vec<VarBind>,
) -> PyResult<Py<PyBytes>> {
    let pdu = if error != 0 {
        ResponsePdu::error(sys_uptime, ResponseError::from(error), index)
    } else {
        ResponsePdu::new(sys_uptime, varbinds)
    };

    let mut body = Vec::new();
    pdu.encode(&mut body)
        .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;

    let header = Header::new(PduType::Response, session_id, transaction_id, packet_id);
    let buf = encode_full_pdu(header, &body);
    Ok(PyBytes::new(py, &buf).into())
}

#[pyfunction]
#[pyo3(signature = (session_id, transaction_id, packet_id, varbinds, context=None))]
pub fn encode_notify_pdu(
    py: Python<'_>,
    session_id: u32,
    transaction_id: u32,
    packet_id: u32,
    varbinds: Vec<VarBind>,
    context: Option<&str>,
) -> PyResult<Py<PyBytes>> {
    let pdu = NotifyPdu::new(varbinds);
    let mut body = Vec::new();

    if let Some(ctx) = context {
        super::pdu::encode_octet_string(&mut body, ctx.as_bytes())
            .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;
    }

    pdu.encode(&mut body)
        .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;

    let mut flags = Flags::NETWORK_BYTE_ORDER;
    if context.is_some() {
        flags |= Flags::NON_DEFAULT_CONTEXT;
    }

    let header =
        Header::new(PduType::Notify, session_id, transaction_id, packet_id).with_flags(flags);
    let buf = encode_full_pdu(header, &body);
    Ok(PyBytes::new(py, &buf).into())
}

#[pyfunction]
pub fn encode_ping_pdu(
    py: Python<'_>,
    session_id: u32,
    transaction_id: u32,
    packet_id: u32,
) -> PyResult<Py<PyBytes>> {
    let pdu = PingPdu::new();
    let mut body = Vec::new();
    pdu.encode(&mut body)
        .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;

    let header = Header::new(PduType::Ping, session_id, transaction_id, packet_id);
    let buf = encode_full_pdu(header, &body);
    Ok(PyBytes::new(py, &buf).into())
}

// Decoding functions

#[pyfunction]
pub fn decode_header(data: &[u8]) -> PyResult<AgentXHeader> {
    if data.len() < HEADER_SIZE {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "Data too short for header",
        ));
    }

    let mut cursor = Cursor::new(data);
    let header = Header::decode(&mut cursor)
        .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;

    Ok(AgentXHeader {
        pdu_type: header.pdu_type as u8,
        flags: header.flags.bits(),
        session_id: header.session_id,
        transaction_id: header.transaction_id,
        packet_id: header.packet_id,
        payload_length: header.payload_length,
    })
}

#[pyfunction]
pub fn decode_response_pdu(data: &[u8], payload_len: usize) -> PyResult<AgentXResponse> {
    let mut cursor = Cursor::new(data);
    let mut response = ResponsePdu::decode(&mut cursor)
        .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;

    // Decode varbinds if there's remaining payload
    if payload_len > 8 {
        let remaining = payload_len - 8;
        let mut varbinds = Vec::new();
        let mut bytes_read = 0;
        while bytes_read < remaining {
            match VarBind::decode(&mut cursor) {
                Ok(vb) => {
                    bytes_read += 8 + vb.oid.len() * 4 + 8;
                    varbinds.push(vb);
                }
                Err(_) => break,
            }
        }
        response.varbinds = varbinds;
    }

    Ok(AgentXResponse {
        sys_uptime: response.sys_uptime,
        error: response.error as u16,
        index: response.index,
        varbinds: response.varbinds,
    })
}

#[pyfunction]
pub fn decode_get_pdu(data: &[u8], payload_len: usize) -> PyResult<AgentXGet> {
    let mut cursor = Cursor::new(data);
    let pdu = GetPdu::decode(&mut cursor, payload_len)
        .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;

    let ranges = pdu
        .ranges
        .into_iter()
        .map(|r| (r.start, r.end, r.include))
        .collect();

    Ok(AgentXGet { ranges })
}

#[pyfunction]
pub fn decode_getbulk_pdu(data: &[u8], payload_len: usize) -> PyResult<AgentXGetBulk> {
    let mut cursor = Cursor::new(data);
    let pdu = GetBulkPdu::decode(&mut cursor, payload_len)
        .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;

    let ranges = pdu
        .ranges
        .into_iter()
        .map(|r| (r.start, r.end, r.include))
        .collect();

    Ok(AgentXGetBulk {
        non_repeaters: pdu.non_repeaters,
        max_repetitions: pdu.max_repetitions,
        ranges,
    })
}

#[pyfunction]
pub fn decode_testset_pdu(data: &[u8], payload_len: usize) -> PyResult<AgentXTestSet> {
    let mut cursor = Cursor::new(data);
    let pdu = TestSetPdu::decode(&mut cursor, payload_len)
        .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;

    Ok(AgentXTestSet {
        varbinds: pdu.varbinds,
    })
}

// PDU type constants for Python
#[pyclass]
pub struct PduTypes;

#[pymethods]
impl PduTypes {
    #[classattr]
    const OPEN: u8 = 1;
    #[classattr]
    const CLOSE: u8 = 2;
    #[classattr]
    const REGISTER: u8 = 3;
    #[classattr]
    const UNREGISTER: u8 = 4;
    #[classattr]
    const GET: u8 = 5;
    #[classattr]
    const GET_NEXT: u8 = 6;
    #[classattr]
    const GET_BULK: u8 = 7;
    #[classattr]
    const TEST_SET: u8 = 8;
    #[classattr]
    const COMMIT_SET: u8 = 9;
    #[classattr]
    const UNDO_SET: u8 = 10;
    #[classattr]
    const CLEANUP_SET: u8 = 11;
    #[classattr]
    const NOTIFY: u8 = 12;
    #[classattr]
    const PING: u8 = 13;
    #[classattr]
    const RESPONSE: u8 = 18;
}

// Close reason constants
#[pyclass]
pub struct CloseReasons;

#[pymethods]
impl CloseReasons {
    #[classattr]
    const OTHER: u8 = 1;
    #[classattr]
    const PARSE_ERROR: u8 = 2;
    #[classattr]
    const PROTOCOL_ERROR: u8 = 3;
    #[classattr]
    const TIMEOUTS: u8 = 4;
    #[classattr]
    const SHUTDOWN: u8 = 5;
    #[classattr]
    const BY_MANAGER: u8 = 6;
}

// Response error constants
#[pyclass]
pub struct ResponseErrors;

#[pymethods]
impl ResponseErrors {
    #[classattr]
    const NO_ERROR: u16 = 0;
    #[classattr]
    const OPEN_FAILED: u16 = 256;
    #[classattr]
    const NOT_OPEN: u16 = 257;
    #[classattr]
    const INDEX_WRONG_TYPE: u16 = 258;
    #[classattr]
    const INDEX_ALREADY_ALLOCATED: u16 = 259;
    #[classattr]
    const INDEX_NONE_AVAILABLE: u16 = 260;
    #[classattr]
    const INDEX_NOT_ALLOCATED: u16 = 261;
    #[classattr]
    const UNSUPPORTED_CONTEXT: u16 = 262;
    #[classattr]
    const DUPLICATE_REGISTRATION: u16 = 263;
    #[classattr]
    const UNKNOWN_REGISTRATION: u16 = 264;
    #[classattr]
    const UNKNOWN_AGENT_CAPS: u16 = 265;
    #[classattr]
    const PARSE_ERROR: u16 = 266;
    #[classattr]
    const REQUEST_DENIED: u16 = 267;
    #[classattr]
    const PROCESSING_ERROR: u16 = 268;
}

pub const HEADER_SIZE_PY: usize = HEADER_SIZE;
