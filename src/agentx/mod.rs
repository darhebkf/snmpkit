pub mod bindings;
pub mod bodies;
pub mod header;
pub mod parallel;
pub mod pdu;

pub use bodies::{
    CleanupSetPdu, ClosePdu, CloseReason, CommitSetPdu, GetBulkPdu, GetPdu, NotifyPdu, OpenPdu,
    PingPdu, RegisterPdu, ResponseError, ResponsePdu, TestSetPdu, UndoSetPdu, UnregisterPdu,
};
pub use header::{AGENTX_VERSION, Flags, HEADER_SIZE, Header, PduType};
pub use parallel::{
    concat_buffers, encode_oids_batch, encode_search_ranges_batch, encode_values_batch,
    encode_varbinds_batch,
};
pub use pdu::{SearchRange, ValueType, VarBind, decode_value, encode_value};

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_exports() {
        // Verify public exports work
        let _h = Header::new(PduType::Open, 0, 0, 0);
        let _f = Flags::NETWORK_BYTE_ORDER;
    }
}
