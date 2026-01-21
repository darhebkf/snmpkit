class SnmpkitError(Exception):
    """Base exception for all snmpkit errors."""


class ConnectionError(SnmpkitError):
    """Failed to connect to or communicate with master agent."""


class RegistrationError(SnmpkitError):
    """Failed to register or unregister OID subtree."""


class EncodingError(SnmpkitError):
    """Failed to encode or decode PDU."""


class TimeoutError(SnmpkitError):
    """Operation timed out."""


class ProtocolError(SnmpkitError):
    """Protocol violation or unexpected response from master agent."""


class SessionError(SnmpkitError):
    """Session not established or was closed unexpectedly."""
