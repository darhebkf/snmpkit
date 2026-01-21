"""Unit Tests for the Agent class."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from snmpkit.agent.agent import Agent, Registration
from snmpkit.agent.set_handler import SetHandler
from snmpkit.agent.updater import Updater
from snmpkit.core import Value


class MockUpdater(Updater):
    """Mock updater for testing."""

    def __init__(self, values=None):
        super().__init__()
        self._mock_values = values or {}

    async def update(self):
        for oid, val in self._mock_values.items():
            self.set_INTEGER(oid, val)


@pytest.fixture
def agent():
    """Create a fresh Agent for each test."""
    return Agent(agent_id="test-agent")


class TestAgentInit:
    """Tests for Agent initialization."""

    def test_default_values(self):
        """Agent initializes with default values."""
        agent = Agent()
        assert agent._agent_id == "snmpkit"
        assert agent._socket_path == "/var/agentx/master"
        assert agent._timeout == 5
        assert agent._parallel_encoding is False
        assert agent._running is False

    def test_custom_values(self):
        """Agent accepts custom initialization values."""
        agent = Agent(
            agent_id="custom",
            socket_path="/custom/path",
            timeout=10,
            parallel_encoding=True,
            worker_threads=4,
            queue_size=100,
        )
        assert agent._agent_id == "custom"
        assert agent._socket_path == "/custom/path"
        assert agent._timeout == 10
        assert agent._parallel_encoding is True
        assert agent._worker_threads == 4
        assert agent._queue_size == 100

    def test_initial_state(self, agent):
        """Agent starts with empty registrations."""
        assert agent._registrations == {}
        assert agent._set_handlers == {}
        assert agent._protocol is None
        assert agent._tasks == []


class TestAgentRegister:
    """Tests for OID registration."""

    def test_register_updater(self, agent):
        """Register stores updater and binds it."""
        updater = MockUpdater()
        agent.register("1.3.6.1.4.1.12345", updater)

        key = "1.3.6.1.4.1.12345:"
        assert key in agent._registrations
        assert agent._registrations[key].oid == "1.3.6.1.4.1.12345"
        assert agent._registrations[key].updater is updater
        assert updater._agent is agent
        assert updater._base_oid == "1.3.6.1.4.1.12345"

    def test_register_with_context(self, agent):
        """Register with context uses context in key."""
        updater = MockUpdater()
        agent.register("1.3.6.1", updater, context="myctx")

        assert "1.3.6.1:myctx" in agent._registrations
        assert "1.3.6.1:" not in agent._registrations

    def test_register_with_freq(self, agent):
        """Register stores frequency."""
        updater = MockUpdater()
        agent.register("1.3.6.1", updater, freq=30)

        reg = agent._registrations["1.3.6.1:"]
        assert reg.freq == 30

    def test_register_with_priority(self, agent):
        """Register stores priority."""
        updater = MockUpdater()
        agent.register("1.3.6.1", updater, priority=50)

        reg = agent._registrations["1.3.6.1:"]
        assert reg.priority == 50

    def test_register_strips_oid(self, agent):
        """Register strips leading/trailing dots and spaces."""
        updater = MockUpdater()
        agent.register(" .1.3.6.1. ", updater)

        assert "1.3.6.1:" in agent._registrations

    def test_register_invalid_oid_raises(self, agent):
        """Register raises ValueError for invalid OID."""
        with pytest.raises(ValueError, match="Invalid OID"):
            agent.register("1.3.abc.1", MockUpdater())

    def test_register_initializes_context(self, agent):
        """Register initializes data store context."""
        updater = MockUpdater()
        agent.register("1.3.6.1", updater, context="ctx1")

        assert "ctx1" in agent._data_store._data


class TestAgentRegisterSet:
    """Tests for SET handler registration."""

    def test_register_set_handler(self, agent):
        """Register SET handler stores and binds it."""
        handler = SetHandler()
        agent.register_set("1.3.6.1.4.1.12345", handler)

        key = "1.3.6.1.4.1.12345:"
        assert key in agent._set_handlers
        assert agent._set_handlers[key] is handler
        assert handler._agent is agent
        assert handler._base_oid == "1.3.6.1.4.1.12345"

    def test_register_set_with_context(self, agent):
        """Register SET handler with context."""
        handler = SetHandler()
        agent.register_set("1.3.6.1", handler, context="setctx")

        assert "1.3.6.1:setctx" in agent._set_handlers

    def test_register_set_invalid_oid_raises(self, agent):
        """Register SET raises ValueError for invalid OID."""
        with pytest.raises(ValueError, match="Invalid OID"):
            agent.register_set("invalid.oid", SetHandler())


class TestAgentUnregister:
    """Tests for OID unregistration."""

    def test_unregister_updater(self, agent):
        """Unregister removes updater registration."""
        agent.register("1.3.6.1", MockUpdater())
        assert "1.3.6.1:" in agent._registrations

        agent.unregister("1.3.6.1")
        assert "1.3.6.1:" not in agent._registrations

    def test_unregister_set_handler(self, agent):
        """Unregister removes SET handler."""
        agent.register_set("1.3.6.1", SetHandler())
        assert "1.3.6.1:" in agent._set_handlers

        agent.unregister("1.3.6.1")
        assert "1.3.6.1:" not in agent._set_handlers

    def test_unregister_with_context(self, agent):
        """Unregister respects context."""
        agent.register("1.3.6.1", MockUpdater(), context="ctx1")
        agent.register("1.3.6.1", MockUpdater(), context="ctx2")

        agent.unregister("1.3.6.1", context="ctx1")

        assert "1.3.6.1:ctx1" not in agent._registrations
        assert "1.3.6.1:ctx2" in agent._registrations

    def test_unregister_nonexistent_silent(self, agent):
        """Unregister non-existent OID does nothing."""
        agent.unregister("1.3.6.1.9.9.9")  # Should not raise


class TestAgentLifecycle:
    """Tests for Agent start/stop lifecycle."""

    async def test_start_already_running_raises(self, agent):
        """Start raises if already running."""
        agent._running = True

        with pytest.raises(RuntimeError, match="already running"):
            await agent.start()

    async def test_stop_not_running_silent(self, agent):
        """Stop does nothing if not running."""
        await agent.stop()  # Should not raise
        assert not agent._running

    async def test_stop_cancels_tasks(self, agent):
        """Stop cancels all running tasks."""
        agent._running = True
        cancelled = False

        async def long_running():
            nonlocal cancelled
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled = True
                raise

        task = asyncio.create_task(long_running())
        agent._tasks = [task]
        await asyncio.sleep(0)  # Let task start

        await agent.stop()

        assert cancelled
        assert agent._tasks == []

    async def test_stop_closes_protocol(self, agent):
        """Stop closes protocol connection."""
        agent._running = True
        mock_protocol = MagicMock()
        mock_protocol.close_session = AsyncMock()
        mock_protocol.disconnect = AsyncMock()
        agent._protocol = mock_protocol

        await agent.stop()

        mock_protocol.close_session.assert_called_once()
        mock_protocol.disconnect.assert_called_once()
        assert agent._protocol is None


class TestAgentSendTrap:
    """Tests for trap sending."""

    async def test_send_trap_not_connected_raises(self, agent):
        """_send_trap raises when not connected."""
        from snmpkit.agent.exceptions import SessionError

        with pytest.raises(SessionError, match="Not connected"):
            await agent._send_trap("1.3.6.1.0.1", [])

    async def test_send_trap_calls_protocol(self, agent):
        """_send_trap calls protocol.send_notify."""
        mock_protocol = MagicMock()
        mock_protocol.send_notify = AsyncMock()
        agent._protocol = mock_protocol

        await agent._send_trap("1.3.6.1.0.1", [])

        mock_protocol.send_notify.assert_called_once()


class TestAgentUpdaterLoop:
    """Tests for the updater loop."""

    async def test_updater_loop_calls_update(self, agent):
        """_updater_loop calls updater.update()."""
        updater = MockUpdater({"1.0": 42})
        agent.register("1.3.6.1", updater)
        reg = agent._registrations["1.3.6.1:"]
        reg.freq = 0.01  # Short interval for test

        agent._running = True

        # Run one iteration then stop
        async def stop_after_delay():
            await asyncio.sleep(0.05)
            agent._running = False

        loop_task = asyncio.create_task(agent._updater_loop(reg))
        stop_task = asyncio.create_task(stop_after_delay())

        await asyncio.gather(loop_task, stop_task)

        # Check data was stored
        vb = agent._data_store.get("1.3.6.1.1.0", None)
        assert vb is not None
        assert vb.value == Value.Integer(42)


class TestRegistrationDataclass:
    """Tests for Registration dataclass."""

    def test_registration_fields(self):
        """Registration stores all fields."""
        updater = MockUpdater()
        reg = Registration(
            oid="1.3.6.1",
            updater=updater,
            freq=10,
            context="ctx",
            priority=100,
        )

        assert reg.oid == "1.3.6.1"
        assert reg.updater is updater
        assert reg.freq == 10
        assert reg.context == "ctx"
        assert reg.priority == 100
