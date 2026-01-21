"""Unit Tests for the SetHandler class."""

import pytest
from snmpkit.agent.set_handler import SetHandler


class MockAgent:
    """Mock agent for testing."""

    pass


@pytest.fixture
def handler():
    """Create a fresh SetHandler."""
    return SetHandler()


@pytest.fixture
def bound_handler():
    """Create a SetHandler bound to a mock agent."""
    h = SetHandler()
    h._bind(MockAgent(), "1.3.6.1.4.1.12345")
    return h


class TestSetHandlerBasic:
    """Basic SetHandler functionality tests."""

    def test_initial_state(self, handler):
        """SetHandler starts with empty state."""
        assert handler._agent is None
        assert handler._base_oid == ""
        assert handler._transactions == {}

    def test_bind(self, handler):
        """Bind sets agent and base OID."""
        agent = MockAgent()
        handler._bind(agent, "1.3.6.1.4.1.12345")

        assert handler._agent is agent
        assert handler._base_oid == "1.3.6.1.4.1.12345"

    def test_make_tid(self, handler):
        """Transaction ID is session_id_transaction_id."""
        tid = handler._make_tid(123, 456)
        assert tid == "123_456"


class TestSetHandlerTransaction:
    """Tests for SET transaction lifecycle."""

    async def test_network_test_stores_transaction(self, bound_handler):
        """_network_test stores the transaction."""
        await bound_handler._network_test(1, 1, "1.3.6.1.4.1.12345.1.0", 42)

        assert "1_1" in bound_handler._transactions
        oid, value = bound_handler._transactions["1_1"]
        assert oid == "1.3.6.1.4.1.12345.1.0"
        assert value == 42

    async def test_network_test_replaces_previous(self, bound_handler):
        """_network_test replaces previous transaction with same ID."""
        await bound_handler._network_test(1, 1, "1.3.6.1.1.0", "first")
        await bound_handler._network_test(1, 1, "1.3.6.1.2.0", "second")

        oid, value = bound_handler._transactions["1_1"]
        assert oid == "1.3.6.1.2.0"
        assert value == "second"

    async def test_network_commit_calls_commit(self, bound_handler):
        """_network_commit calls commit method."""
        commits = []

        class TrackedHandler(SetHandler):
            async def commit(self, oid, value):
                commits.append((oid, value))

        handler = TrackedHandler()
        handler._bind(MockAgent(), "1.3.6.1")
        await handler._network_test(1, 1, "1.3.6.1.1.0", 42)
        await handler._network_commit(1, 1)

        assert commits == [("1.3.6.1.1.0", 42)]
        assert "1_1" not in handler._transactions

    async def test_network_commit_no_transaction(self, bound_handler):
        """_network_commit does nothing if no transaction."""
        # Should not raise
        await bound_handler._network_commit(1, 999)

    async def test_network_undo_calls_undo(self, bound_handler):
        """_network_undo calls undo method."""
        undos = []

        class TrackedHandler(SetHandler):
            async def undo(self, oid):
                undos.append(oid)

        handler = TrackedHandler()
        handler._bind(MockAgent(), "1.3.6.1")
        await handler._network_test(1, 1, "1.3.6.1.1.0", 42)
        await handler._network_undo(1, 1)

        assert undos == ["1.3.6.1.1.0"]
        assert "1_1" not in handler._transactions

    async def test_network_cleanup_calls_cleanup(self, bound_handler):
        """_network_cleanup calls cleanup method."""
        cleanups = []

        class TrackedHandler(SetHandler):
            async def cleanup(self, oid):
                cleanups.append(oid)

        handler = TrackedHandler()
        handler._bind(MockAgent(), "1.3.6.1")
        await handler._network_test(1, 1, "1.3.6.1.1.0", 42)
        await handler._network_cleanup(1, 1)

        assert cleanups == ["1.3.6.1.1.0"]
        assert "1_1" not in handler._transactions


class TestSetHandlerLifecycle:
    """Tests for complete SET transaction lifecycles."""

    async def test_successful_set(self):
        """Complete successful SET: test -> commit."""
        log = []

        class LoggingHandler(SetHandler):
            async def test(self, oid, value):
                log.append(("test", oid, value))

            async def commit(self, oid, value):
                log.append(("commit", oid, value))

        handler = LoggingHandler()
        handler._bind(MockAgent(), "1.3.6.1")

        await handler._network_test(1, 1, "1.3.6.1.1.0", 42)
        await handler._network_commit(1, 1)

        assert log == [
            ("test", "1.3.6.1.1.0", 42),
            ("commit", "1.3.6.1.1.0", 42),
        ]

    async def test_failed_set_with_undo(self):
        """Failed SET: test -> undo."""
        log = []

        class LoggingHandler(SetHandler):
            async def test(self, oid, value):
                log.append(("test", oid, value))

            async def undo(self, oid):
                log.append(("undo", oid))

        handler = LoggingHandler()
        handler._bind(MockAgent(), "1.3.6.1")

        await handler._network_test(1, 1, "1.3.6.1.1.0", 42)
        await handler._network_undo(1, 1)

        assert log == [
            ("test", "1.3.6.1.1.0", 42),
            ("undo", "1.3.6.1.1.0"),
        ]

    async def test_cleanup_after_commit(self):
        """Cleanup after commit."""
        log = []

        class LoggingHandler(SetHandler):
            async def test(self, oid, value):
                log.append(("test", oid, value))

            async def commit(self, oid, value):
                log.append(("commit", oid, value))

            async def cleanup(self, oid):
                log.append(("cleanup", oid))

        handler = LoggingHandler()
        handler._bind(MockAgent(), "1.3.6.1")

        await handler._network_test(1, 1, "1.3.6.1.1.0", 42)
        await handler._network_commit(1, 1)
        # Cleanup called on new test after commit
        await handler._network_test(1, 2, "1.3.6.1.1.0", 100)
        await handler._network_cleanup(1, 2)

        assert ("cleanup", "1.3.6.1.1.0") in log


class TestSetHandlerRejection:
    """Tests for SET rejection via exceptions."""

    async def test_test_exception_rejects(self):
        """Exception in test() rejects the SET."""

        class RejectingHandler(SetHandler):
            async def test(self, oid, value):
                raise ValueError("Invalid value")

        handler = RejectingHandler()
        handler._bind(MockAgent(), "1.3.6.1")

        with pytest.raises(ValueError, match="Invalid value"):
            await handler._network_test(1, 1, "1.3.6.1.1.0", 42)

        # Transaction should not be stored on failure
        assert "1_1" not in handler._transactions


class TestSetHandlerMultipleTransactions:
    """Tests for handling multiple concurrent transactions."""

    async def test_different_sessions(self):
        """Different sessions have separate transactions."""
        handler = SetHandler()
        handler._bind(MockAgent(), "1.3.6.1")

        await handler._network_test(1, 1, "1.3.6.1.1.0", "session1")
        await handler._network_test(2, 1, "1.3.6.1.2.0", "session2")

        assert handler._transactions["1_1"][1] == "session1"
        assert handler._transactions["2_1"][1] == "session2"

    async def test_different_transaction_ids(self):
        """Different transaction IDs are tracked separately."""
        handler = SetHandler()
        handler._bind(MockAgent(), "1.3.6.1")

        await handler._network_test(1, 1, "1.3.6.1.1.0", "tx1")
        await handler._network_test(1, 2, "1.3.6.1.2.0", "tx2")

        assert handler._transactions["1_1"][1] == "tx1"
        assert handler._transactions["1_2"][1] == "tx2"


class TestSetHandlerDefaultMethods:
    """Tests for default method implementations."""

    async def test_default_test_passes(self, bound_handler):
        """Default test() does nothing (accepts all)."""
        await bound_handler.test("1.3.6.1.1.0", 42)  # Should not raise

    async def test_default_commit_passes(self, bound_handler):
        """Default commit() does nothing."""
        await bound_handler.commit("1.3.6.1.1.0", 42)  # Should not raise

    async def test_default_undo_passes(self, bound_handler):
        """Default undo() does nothing."""
        await bound_handler.undo("1.3.6.1.1.0")  # Should not raise

    async def test_default_cleanup_passes(self, bound_handler):
        """Default cleanup() does nothing."""
        await bound_handler.cleanup("1.3.6.1.1.0")  # Should not raise
