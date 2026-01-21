"""Unit Tests for the RequestHandler class."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from snmpkit.agent.handlers import NOT_WRITABLE, WRONG_VALUE, DataStore, RequestHandler
from snmpkit.agent.set_handler import SetHandler
from snmpkit.core import Oid, Value, VarBind


def vb(oid_str: str, value: int = 0) -> VarBind:
    """Helper to create VarBind with Integer value."""
    return VarBind(Oid(oid_str), Value.Integer(value))


class MockHeader:
    """Mock PDU header."""

    def __init__(self, session_id=1, transaction_id=1, payload_length=100):
        self.session_id = session_id
        self.transaction_id = transaction_id
        self.payload_length = payload_length


class MockGetPdu:
    """Mock GET/GETNEXT PDU."""

    def __init__(self, ranges):
        # ranges: list of (start_oid, end_oid, include)
        self.ranges = [(Oid(s), Oid(e) if e else None, i) for s, e, i in ranges]


class MockBulkPdu:
    """Mock GETBULK PDU."""

    def __init__(self, ranges, non_repeaters=0, max_repetitions=10):
        self.ranges = [(Oid(s), Oid(e) if e else None, i) for s, e, i in ranges]
        self.non_repeaters = non_repeaters
        self.max_repetitions = max_repetitions


class MockTestSetPdu:
    """Mock TESTSET PDU."""

    def __init__(self, varbinds):
        self.varbinds = varbinds


@pytest.fixture
def data_store():
    """Create a DataStore with test data."""
    store = DataStore()
    store.update(
        "1.3.6.1.2.1.1",
        None,
        [
            vb("1.3.6.1.2.1.1.1.0", 1),
            vb("1.3.6.1.2.1.1.2.0", 2),
            vb("1.3.6.1.2.1.1.3.0", 3),
        ],
    )
    return store


@pytest.fixture
def protocol():
    """Create a mock protocol."""
    p = MagicMock()
    p.send_response = AsyncMock()
    return p


@pytest.fixture
def handler(protocol, data_store):
    """Create a RequestHandler with empty set handlers."""
    return RequestHandler(protocol, data_store, {})


class TestRequestHandlerGet:
    """Tests for GET request handling."""

    async def test_get_single_oid(self, handler, protocol):
        """GET single existing OID."""
        with patch("snmpkit.agent.handlers.decode_get_pdu") as mock_decode:
            mock_decode.return_value = MockGetPdu([("1.3.6.1.2.1.1.1.0", "", False)])

            await handler.handle_get(MockHeader(), b"")

            protocol.send_response.assert_called_once()
            header, varbinds = protocol.send_response.call_args.args
            assert len(varbinds) == 1
            assert varbinds[0].value == Value.Integer(1)

    async def test_get_multiple_oids(self, handler, protocol):
        """GET multiple existing OIDs."""
        with patch("snmpkit.agent.handlers.decode_get_pdu") as mock_decode:
            mock_decode.return_value = MockGetPdu(
                [
                    ("1.3.6.1.2.1.1.1.0", "", False),
                    ("1.3.6.1.2.1.1.3.0", "", False),
                ]
            )

            await handler.handle_get(MockHeader(), b"")

            varbinds = protocol.send_response.call_args.args[1]
            assert len(varbinds) == 2
            assert varbinds[0].value == Value.Integer(1)
            assert varbinds[1].value == Value.Integer(3)

    async def test_get_missing_oid(self, handler, protocol):
        """GET non-existent OID returns NoSuchObject."""
        with patch("snmpkit.agent.handlers.decode_get_pdu") as mock_decode:
            mock_decode.return_value = MockGetPdu([("1.3.6.1.2.1.1.99.0", "", False)])

            await handler.handle_get(MockHeader(), b"")

            varbinds = protocol.send_response.call_args.args[1]
            assert len(varbinds) == 1
            assert varbinds[0].value == Value.NoSuchObject()


class TestRequestHandlerGetNext:
    """Tests for GETNEXT request handling."""

    async def test_getnext_basic(self, handler, protocol):
        """GETNEXT returns next OID in sequence."""
        with patch("snmpkit.agent.handlers.decode_get_pdu") as mock_decode:
            mock_decode.return_value = MockGetPdu([("1.3.6.1.2.1.1.1.0", "", False)])

            await handler.handle_getnext(MockHeader(), b"")

            varbinds = protocol.send_response.call_args.args[1]
            assert len(varbinds) == 1
            assert str(varbinds[0].oid) == "1.3.6.1.2.1.1.2.0"
            assert varbinds[0].value == Value.Integer(2)

    async def test_getnext_past_last(self, handler, protocol):
        """GETNEXT past last OID returns EndOfMibView."""
        with patch("snmpkit.agent.handlers.decode_get_pdu") as mock_decode:
            mock_decode.return_value = MockGetPdu([("1.3.6.1.2.1.1.3.0", "", False)])

            await handler.handle_getnext(MockHeader(), b"")

            varbinds = protocol.send_response.call_args.args[1]
            assert varbinds[0].value == Value.EndOfMibView()

    async def test_getnext_from_prefix(self, handler, protocol):
        """GETNEXT from prefix OID returns first child."""
        with patch("snmpkit.agent.handlers.decode_get_pdu") as mock_decode:
            mock_decode.return_value = MockGetPdu([("1.3.6.1.2.1.1.0", "", False)])

            await handler.handle_getnext(MockHeader(), b"")

            varbinds = protocol.send_response.call_args.args[1]
            assert str(varbinds[0].oid) == "1.3.6.1.2.1.1.1.0"

    async def test_getnext_with_end_oid(self, handler, protocol):
        """GETNEXT respects end_oid boundary."""
        with patch("snmpkit.agent.handlers.decode_get_pdu") as mock_decode:
            # End at 1.3.6.1.2.1.1.2.0
            mock_decode.return_value = MockGetPdu(
                [("1.3.6.1.2.1.1.1.0", "1.3.6.1.2.1.1.2.0", False)]
            )

            await handler.handle_getnext(MockHeader(), b"")

            varbinds = protocol.send_response.call_args.args[1]
            assert str(varbinds[0].oid) == "1.3.6.1.2.1.1.2.0"


class TestRequestHandlerGetBulk:
    """Tests for GETBULK request handling."""

    async def test_getbulk_non_repeaters(self, handler, protocol):
        """GETBULK handles non-repeaters like GETNEXT."""
        with patch("snmpkit.agent.handlers.decode_getbulk_pdu") as mock_decode:
            mock_decode.return_value = MockBulkPdu(
                [("1.3.6.1.2.1.1.1.0", "", False)],
                non_repeaters=1,
                max_repetitions=10,
            )

            await handler.handle_getbulk(MockHeader(), b"")

            varbinds = protocol.send_response.call_args.args[1]
            assert len(varbinds) == 1
            assert str(varbinds[0].oid) == "1.3.6.1.2.1.1.2.0"

    async def test_getbulk_repeaters(self, handler, protocol):
        """GETBULK repeaters return multiple values."""
        with patch("snmpkit.agent.handlers.decode_getbulk_pdu") as mock_decode:
            mock_decode.return_value = MockBulkPdu(
                [("1.3.6.1.2.1.1.0", "", False)],  # Before first OID
                non_repeaters=0,
                max_repetitions=10,
            )

            await handler.handle_getbulk(MockHeader(), b"")

            varbinds = protocol.send_response.call_args.args[1]
            # Should get all 3 values plus EndOfMibView
            assert len(varbinds) == 4
            assert varbinds[0].value == Value.Integer(1)
            assert varbinds[1].value == Value.Integer(2)
            assert varbinds[2].value == Value.Integer(3)
            assert varbinds[3].value == Value.EndOfMibView()

    async def test_getbulk_max_repetitions_limits(self, handler, protocol):
        """GETBULK respects max_repetitions limit."""
        with patch("snmpkit.agent.handlers.decode_getbulk_pdu") as mock_decode:
            mock_decode.return_value = MockBulkPdu(
                [("1.3.6.1.2.1.1.0", "", False)],
                non_repeaters=0,
                max_repetitions=2,
            )

            await handler.handle_getbulk(MockHeader(), b"")

            varbinds = protocol.send_response.call_args.args[1]
            assert len(varbinds) == 2
            assert varbinds[0].value == Value.Integer(1)
            assert varbinds[1].value == Value.Integer(2)


class TestRequestHandlerSet:
    """Tests for SET request handling (TestSet, CommitSet, UndoSet, CleanupSet)."""

    @pytest.fixture
    def set_handler(self):
        """Create a mock SetHandler."""
        h = SetHandler()
        h._bind(MagicMock(), "1.3.6.1.2.1.1")
        h._network_test = AsyncMock()
        h._network_commit = AsyncMock()
        h._network_undo = AsyncMock()
        h._network_cleanup = AsyncMock()
        return h

    @pytest.fixture
    def handler_with_set(self, protocol, data_store, set_handler):
        """Create RequestHandler with a SetHandler registered."""
        return RequestHandler(
            protocol,
            data_store,
            {"1.3.6.1.2.1.1:": set_handler},
        )

    async def test_testset_success(self, handler_with_set, protocol, set_handler):
        """TESTSET calls handler._network_test."""
        with patch("snmpkit.agent.handlers.decode_testset_pdu") as mock_decode:
            mock_decode.return_value = MockTestSetPdu([vb("1.3.6.1.2.1.1.1.0", 42)])

            await handler_with_set.handle_testset(MockHeader(), b"")

            set_handler._network_test.assert_called_once()
            # No error
            protocol.send_response.assert_called_once()
            kwargs = protocol.send_response.call_args.kwargs
            assert kwargs.get("error", 0) == 0

    async def test_testset_not_writable(self, handler, protocol):
        """TESTSET returns NOT_WRITABLE for unregistered OID."""
        with patch("snmpkit.agent.handlers.decode_testset_pdu") as mock_decode:
            mock_decode.return_value = MockTestSetPdu(
                [
                    vb("1.3.6.1.9.9.9.0", 42)  # No handler for this OID
                ]
            )

            await handler.handle_testset(MockHeader(), b"")

            kwargs = protocol.send_response.call_args.kwargs
            assert kwargs.get("error") == NOT_WRITABLE
            assert kwargs.get("index") == 1

    async def test_testset_wrong_value(self, handler_with_set, protocol, set_handler):
        """TESTSET returns WRONG_VALUE when handler raises."""
        set_handler._network_test.side_effect = ValueError("Invalid")

        with patch("snmpkit.agent.handlers.decode_testset_pdu") as mock_decode:
            mock_decode.return_value = MockTestSetPdu([vb("1.3.6.1.2.1.1.1.0", 42)])

            await handler_with_set.handle_testset(MockHeader(), b"")

            kwargs = protocol.send_response.call_args.kwargs
            assert kwargs.get("error") == WRONG_VALUE

    async def test_commitset(self, handler_with_set, protocol, set_handler):
        """COMMITSET calls handler._network_commit."""
        await handler_with_set.handle_commitset(MockHeader())

        set_handler._network_commit.assert_called_once()
        protocol.send_response.assert_called_once()

    async def test_undoset(self, handler_with_set, protocol, set_handler):
        """UNDOSET calls handler._network_undo."""
        await handler_with_set.handle_undoset(MockHeader())

        set_handler._network_undo.assert_called_once()
        protocol.send_response.assert_called_once()

    async def test_cleanupset(self, handler_with_set, protocol, set_handler):
        """CLEANUPSET calls handler._network_cleanup."""
        await handler_with_set.handle_cleanupset(MockHeader())

        set_handler._network_cleanup.assert_called_once()
        protocol.send_response.assert_called_once()


class TestRequestHandlerFindSetHandler:
    """Tests for _find_set_handler method."""

    def test_find_exact_match(self, protocol, data_store):
        """Find handler for exact OID prefix match."""
        mock_handler = MagicMock()
        handler = RequestHandler(
            protocol,
            data_store,
            {"1.3.6.1.2.1.1:": mock_handler},
        )

        result = handler._find_set_handler("1.3.6.1.2.1.1.1.0")
        assert result is mock_handler

    def test_find_no_match(self, protocol, data_store):
        """Return None when no handler matches."""
        handler = RequestHandler(
            protocol,
            data_store,
            {"1.3.6.1.2.1.1:": MagicMock()},
        )

        result = handler._find_set_handler("1.3.6.1.9.9.9.0")
        assert result is None

    def test_find_multiple_handlers(self, protocol, data_store):
        """Find correct handler among multiple registrations."""
        handler1 = MagicMock()
        handler2 = MagicMock()
        handler = RequestHandler(
            protocol,
            data_store,
            {
                "1.3.6.1.2.1.1:": handler1,
                "1.3.6.1.4.1:": handler2,
            },
        )

        assert handler._find_set_handler("1.3.6.1.2.1.1.5.0") is handler1
        assert handler._find_set_handler("1.3.6.1.4.1.12345.0") is handler2
