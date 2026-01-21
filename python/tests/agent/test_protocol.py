"""Unit Tests for the Protocol class."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from snmpkit.agent.exceptions import ConnectionError, ProtocolError, RegistrationError, SessionError
from snmpkit.agent.protocol import Protocol
from snmpkit.core import Oid, PduTypes, Value, VarBind


class MockHeader:
    """Mock PDU header."""

    def __init__(
        self,
        pdu_type=PduTypes.RESPONSE,
        session_id=1,
        transaction_id=1,
        packet_id=1,
        payload_length=0,
    ):
        self.pdu_type = pdu_type
        self.session_id = session_id
        self.transaction_id = transaction_id
        self.packet_id = packet_id
        self.payload_length = payload_length


class MockResponse:
    """Mock decoded response."""

    def __init__(self, error=0, is_error=False):
        self.error = error
        self.is_error = is_error


@pytest.fixture
def protocol():
    """Create a fresh Protocol for each test."""
    return Protocol("test-agent", "/var/agentx/master", 5)


class TestProtocolInit:
    """Tests for Protocol initialization."""

    def test_default_values(self, protocol):
        """Protocol initializes with correct values."""
        assert protocol._agent_id == "test-agent"
        assert protocol._socket_path == "/var/agentx/master"
        assert protocol._timeout == 5
        assert protocol._session_id == 0
        assert protocol._transaction_id == 0
        assert protocol._packet_id == 0

    def test_session_id_property(self, protocol):
        """session_id property returns _session_id."""
        protocol._session_id = 42
        assert protocol.session_id == 42


class TestProtocolIdCounters:
    """Tests for packet and transaction ID counters."""

    def test_next_packet_id_increments(self, protocol):
        """_next_packet_id increments and returns."""
        assert protocol._next_packet_id() == 1
        assert protocol._next_packet_id() == 2
        assert protocol._next_packet_id() == 3

    def test_next_transaction_id_increments(self, protocol):
        """_next_transaction_id increments and returns."""
        assert protocol._next_transaction_id() == 1
        assert protocol._next_transaction_id() == 2
        assert protocol._next_transaction_id() == 3


class TestProtocolSend:
    """Tests for send method."""

    async def test_send_not_connected_raises(self, protocol):
        """send raises SessionError when not connected."""
        with pytest.raises(SessionError, match="Not connected"):
            await protocol.send(b"test")

    async def test_send_writes_data(self, protocol):
        """send writes data and drains."""
        mock_writer = MagicMock()
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        protocol._writer = mock_writer

        await protocol.send(b"test data")

        mock_writer.write.assert_called_once_with(b"test data")
        mock_writer.drain.assert_called_once()


class TestProtocolRecvPdu:
    """Tests for recv_pdu method."""

    async def test_recv_pdu_not_connected_raises(self, protocol):
        """recv_pdu raises SessionError when not connected."""
        with pytest.raises(SessionError, match="Not connected"):
            await protocol.recv_pdu()

    async def test_recv_pdu_timeout_returns_none(self, protocol):
        """recv_pdu returns None on timeout."""
        mock_reader = MagicMock()

        async def timeout_read(*args, **kwargs):
            raise asyncio.TimeoutError()

        mock_reader.read = timeout_read
        protocol._reader = mock_reader

        result = await protocol.recv_pdu(timeout=0.01)
        assert result is None


class TestProtocolOpenSession:
    """Tests for open_session method."""

    async def test_open_session_success(self, protocol):
        """open_session establishes session on success."""
        protocol._writer = MagicMock()
        protocol._writer.write = MagicMock()
        protocol._writer.drain = AsyncMock()

        with patch.object(protocol, "recv_pdu") as mock_recv:
            mock_recv.return_value = (MockHeader(session_id=42), b"")
            with patch("snmpkit.agent.protocol.decode_response_pdu") as mock_decode:
                mock_decode.return_value = MockResponse(is_error=False)

                await protocol.open_session()

        assert protocol._session_id == 42

    async def test_open_session_no_response_raises(self, protocol):
        """open_session raises ConnectionError on no response."""
        protocol._writer = MagicMock()
        protocol._writer.write = MagicMock()
        protocol._writer.drain = AsyncMock()

        with patch.object(protocol, "recv_pdu", return_value=None):
            with pytest.raises(ConnectionError, match="No response"):
                await protocol.open_session()

    async def test_open_session_wrong_pdu_type_raises(self, protocol):
        """open_session raises ProtocolError on wrong PDU type."""
        protocol._writer = MagicMock()
        protocol._writer.write = MagicMock()
        protocol._writer.drain = AsyncMock()

        with patch.object(protocol, "recv_pdu") as mock_recv:
            mock_recv.return_value = (MockHeader(pdu_type=PduTypes.GET), b"")
            with pytest.raises(ProtocolError, match="Expected Response"):
                await protocol.open_session()

    async def test_open_session_error_response_raises(self, protocol):
        """open_session raises ConnectionError on error response."""
        protocol._writer = MagicMock()
        protocol._writer.write = MagicMock()
        protocol._writer.drain = AsyncMock()

        with patch.object(protocol, "recv_pdu") as mock_recv:
            mock_recv.return_value = (MockHeader(), b"")
            with patch("snmpkit.agent.protocol.decode_response_pdu") as mock_decode:
                mock_decode.return_value = MockResponse(error=256, is_error=True)
                with pytest.raises(ConnectionError, match="Open failed"):
                    await protocol.open_session()


class TestProtocolCloseSession:
    """Tests for close_session method."""

    async def test_close_session_no_session_noop(self, protocol):
        """close_session does nothing if no session."""
        await protocol.close_session()  # Should not raise

    async def test_close_session_sends_close_pdu(self, protocol):
        """close_session sends Close PDU."""
        protocol._session_id = 42
        protocol._writer = MagicMock()
        protocol._writer.write = MagicMock()
        protocol._writer.drain = AsyncMock()

        await protocol.close_session()

        protocol._writer.write.assert_called_once()
        assert protocol._session_id == 0


class TestProtocolPing:
    """Tests for ping method."""

    async def test_ping_success(self, protocol):
        """ping succeeds on valid response."""
        protocol._session_id = 1
        protocol._writer = MagicMock()
        protocol._writer.write = MagicMock()
        protocol._writer.drain = AsyncMock()

        with patch.object(protocol, "recv_pdu") as mock_recv:
            mock_recv.return_value = (MockHeader(), b"")
            await protocol.ping()  # Should not raise

    async def test_ping_no_response_raises(self, protocol):
        """ping raises ConnectionError on no response."""
        protocol._session_id = 1
        protocol._writer = MagicMock()
        protocol._writer.write = MagicMock()
        protocol._writer.drain = AsyncMock()

        with patch.object(protocol, "recv_pdu", return_value=None):
            with pytest.raises(ConnectionError, match="No response"):
                await protocol.ping()


class TestProtocolRegisterOid:
    """Tests for register_oid method."""

    @pytest.fixture
    def mock_registration(self):
        """Create a mock Registration."""
        reg = MagicMock()
        reg.oid = "1.3.6.1.4.1.12345"
        reg.priority = 127
        reg.context = None
        return reg

    async def test_register_oid_success(self, protocol, mock_registration):
        """register_oid succeeds on valid response."""
        protocol._session_id = 1
        protocol._writer = MagicMock()
        protocol._writer.write = MagicMock()
        protocol._writer.drain = AsyncMock()

        with patch.object(protocol, "recv_pdu") as mock_recv:
            mock_recv.return_value = (MockHeader(), b"")
            with patch("snmpkit.agent.protocol.decode_response_pdu") as mock_decode:
                mock_decode.return_value = MockResponse(is_error=False)
                await protocol.register_oid(mock_registration)

    async def test_register_oid_no_response_raises(self, protocol, mock_registration):
        """register_oid raises RegistrationError on no response."""
        protocol._session_id = 1
        protocol._writer = MagicMock()
        protocol._writer.write = MagicMock()
        protocol._writer.drain = AsyncMock()

        with patch.object(protocol, "recv_pdu", return_value=None):
            with pytest.raises(RegistrationError, match="No response"):
                await protocol.register_oid(mock_registration)

    async def test_register_oid_error_response_raises(self, protocol, mock_registration):
        """register_oid raises RegistrationError on error response."""
        protocol._session_id = 1
        protocol._writer = MagicMock()
        protocol._writer.write = MagicMock()
        protocol._writer.drain = AsyncMock()

        with patch.object(protocol, "recv_pdu") as mock_recv:
            mock_recv.return_value = (MockHeader(), b"")
            with patch("snmpkit.agent.protocol.decode_response_pdu") as mock_decode:
                mock_decode.return_value = MockResponse(error=263, is_error=True)
                with pytest.raises(RegistrationError, match="Registration failed"):
                    await protocol.register_oid(mock_registration)


class TestProtocolSendResponse:
    """Tests for send_response method."""

    async def test_send_response_encodes_and_sends(self, protocol):
        """send_response encodes PDU and sends."""
        protocol._writer = MagicMock()
        protocol._writer.write = MagicMock()
        protocol._writer.drain = AsyncMock()

        header = MockHeader(session_id=1, transaction_id=2, packet_id=3)
        varbinds = [VarBind(Oid("1.3.6.1"), Value.Integer(42))]

        await protocol.send_response(header, varbinds)

        protocol._writer.write.assert_called_once()
        protocol._writer.drain.assert_called_once()


class TestProtocolSendNotify:
    """Tests for send_notify method."""

    async def test_send_notify_encodes_and_sends(self, protocol):
        """send_notify encodes Notify PDU and sends."""
        protocol._session_id = 1
        protocol._writer = MagicMock()
        protocol._writer.write = MagicMock()
        protocol._writer.drain = AsyncMock()

        varbinds = [VarBind(Oid("1.3.6.1.0.1"), Value.Integer(1))]
        await protocol.send_notify(varbinds)

        protocol._writer.write.assert_called_once()
        protocol._writer.drain.assert_called_once()


class TestProtocolDisconnect:
    """Tests for disconnect method."""

    async def test_disconnect_closes_writer(self, protocol):
        """disconnect closes the writer."""
        mock_writer = MagicMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        protocol._writer = mock_writer
        protocol._reader = MagicMock()

        await protocol.disconnect()

        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_called_once()
        assert protocol._writer is None
        assert protocol._reader is None

    async def test_disconnect_clears_buffer(self, protocol):
        """disconnect clears receive buffer."""
        protocol._recv_buf = b"leftover data"
        protocol._writer = MagicMock()
        protocol._writer.close = MagicMock()
        protocol._writer.wait_closed = AsyncMock()

        await protocol.disconnect()

        assert protocol._recv_buf == b""
