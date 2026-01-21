"""Unit Tests for the Updater class."""

import pytest
from snmpkit.agent.updater import Updater
from snmpkit.core import Oid, Value, VarBind


class MockAgent:
    """Mock agent for testing Updater without network."""

    def __init__(self):
        self.traps_sent = []

    async def _send_trap(self, oid: str, varbinds: list) -> None:
        self.traps_sent.append((oid, varbinds))


@pytest.fixture
def updater():
    """Create a fresh Updater for each test."""
    return Updater()


@pytest.fixture
def bound_updater():
    """Create an Updater bound to a mock agent."""
    u = Updater()
    agent = MockAgent()
    u._bind(agent, "1.3.6.1.4.1.12345")
    return u, agent


class TestUpdaterBasic:
    """Basic Updater functionality tests."""

    def test_initial_state(self, updater):
        """Updater starts with empty state."""
        assert updater._values == {}
        assert updater._agent is None
        assert updater._base_oid == ""

    def test_bind(self, updater):
        """Bind sets agent and base OID."""
        agent = MockAgent()
        updater._bind(agent, "1.3.6.1.4.1.12345")

        assert updater._agent is agent
        assert updater._base_oid == "1.3.6.1.4.1.12345"

    def test_clear(self, updater):
        """Clear removes all values."""
        updater.set_INTEGER("1.0", 42)
        updater.set_OCTETSTRING("2.0", b"test")
        assert len(updater._values) == 2

        updater.clear()
        assert updater._values == {}


class TestUpdaterSetMethods:
    """Tests for set_* value methods."""

    def test_set_integer(self, updater):
        """set_INTEGER stores Integer value."""
        updater.set_INTEGER("1.0", 42)
        assert updater._values["1.0"] == Value.Integer(42)

    def test_set_integer_negative(self, updater):
        """set_INTEGER handles negative values."""
        updater.set_INTEGER("1.0", -12345)
        assert updater._values["1.0"] == Value.Integer(-12345)

    def test_set_octetstring_bytes(self, updater):
        """set_OCTETSTRING stores bytes."""
        updater.set_OCTETSTRING("1.0", b"hello")
        assert updater._values["1.0"] == Value.OctetString(b"hello")

    def test_set_octetstring_str(self, updater):
        """set_OCTETSTRING converts str to UTF-8 bytes."""
        updater.set_OCTETSTRING("1.0", "hello")
        assert updater._values["1.0"] == Value.OctetString(b"hello")

    def test_set_octetstring_unicode(self, updater):
        """set_OCTETSTRING handles unicode."""
        updater.set_OCTETSTRING("1.0", "héllo")
        assert updater._values["1.0"] == Value.OctetString("héllo".encode("utf-8"))

    def test_set_objectidentifier(self, updater):
        """set_OBJECTIDENTIFIER stores OID value."""
        updater.set_OBJECTIDENTIFIER("1.0", "1.3.6.1.4.1.12345")
        assert updater._values["1.0"] == Value.ObjectIdentifier(Oid("1.3.6.1.4.1.12345"))

    def test_set_ipaddress(self, updater):
        """set_IPADDRESS stores IP address."""
        updater.set_IPADDRESS("1.0", "192.168.1.1")
        assert updater._values["1.0"] == Value.IpAddress(192, 168, 1, 1)

    def test_set_ipaddress_invalid(self, updater):
        """set_IPADDRESS rejects invalid IP."""
        with pytest.raises(ValueError):
            updater.set_IPADDRESS("1.0", "192.168.1")  # Missing octet

    def test_set_counter32(self, updater):
        """set_COUNTER32 stores Counter32 value."""
        updater.set_COUNTER32("1.0", 4294967295)
        assert updater._values["1.0"] == Value.Counter32(4294967295)

    def test_set_gauge32(self, updater):
        """set_GAUGE32 stores Gauge32 value."""
        updater.set_GAUGE32("1.0", 1000000)
        assert updater._values["1.0"] == Value.Gauge32(1000000)

    def test_set_timeticks(self, updater):
        """set_TIMETICKS stores TimeTicks value."""
        updater.set_TIMETICKS("1.0", 123456789)
        assert updater._values["1.0"] == Value.TimeTicks(123456789)

    def test_set_opaque(self, updater):
        """set_OPAQUE stores Opaque value."""
        updater.set_OPAQUE("1.0", b"\x00\x01\x02\x03")
        assert updater._values["1.0"] == Value.Opaque(b"\x00\x01\x02\x03")

    def test_set_counter64(self, updater):
        """set_COUNTER64 stores Counter64 value."""
        big_val = 2**63 + 12345
        updater.set_COUNTER64("1.0", big_val)
        assert updater._values["1.0"] == Value.Counter64(big_val)


class TestUpdaterGetValue:
    """Tests for get_value method."""

    def test_get_value_exists(self, updater):
        """get_value returns stored value."""
        updater.set_INTEGER("1.0", 42)
        assert updater.get_value("1.0") == Value.Integer(42)

    def test_get_value_missing(self, updater):
        """get_value returns None for missing OID."""
        assert updater.get_value("1.0") is None


class TestUpdaterGetVarbinds:
    """Tests for get_varbinds method."""

    def test_get_varbinds_empty(self, updater):
        """get_varbinds returns empty list when no values."""
        assert updater.get_varbinds() == []

    def test_get_varbinds_without_base_oid(self, updater):
        """get_varbinds uses OID suffix when not bound."""
        updater.set_INTEGER("1.0", 42)
        varbinds = updater.get_varbinds()

        assert len(varbinds) == 1
        assert str(varbinds[0].oid) == "1.0"
        assert varbinds[0].value == Value.Integer(42)

    def test_get_varbinds_with_base_oid(self, bound_updater):
        """get_varbinds prepends base OID."""
        updater, _ = bound_updater
        updater.set_INTEGER("1.0", 42)
        varbinds = updater.get_varbinds()

        assert len(varbinds) == 1
        assert str(varbinds[0].oid) == "1.3.6.1.4.1.12345.1.0"

    def test_get_varbinds_multiple(self, bound_updater):
        """get_varbinds returns all values."""
        updater, _ = bound_updater
        updater.set_INTEGER("1.0", 42)
        updater.set_OCTETSTRING("2.0", b"test")
        updater.set_COUNTER64("3.0", 12345)

        varbinds = updater.get_varbinds()
        assert len(varbinds) == 3

    def test_get_varbinds_returns_varbind_objects(self, bound_updater):
        """get_varbinds returns VarBind instances."""
        updater, _ = bound_updater
        updater.set_INTEGER("1.0", 42)
        varbinds = updater.get_varbinds()

        assert isinstance(varbinds[0], VarBind)
        assert isinstance(varbinds[0].oid, Oid)
        assert isinstance(varbinds[0].value, Value)


class TestUpdaterTrap:
    """Tests for trap sending."""

    async def test_send_trap(self, bound_updater):
        """send_trap calls agent._send_trap."""
        updater, agent = bound_updater

        vb = VarBind(Oid("1.3.6.1.4.1.12345.1.0"), Value.Integer(42))
        await updater.send_trap("1.3.6.1.4.1.12345.0.1", vb)

        assert len(agent.traps_sent) == 1
        trap_oid, trap_varbinds = agent.traps_sent[0]
        assert trap_oid == "1.3.6.1.4.1.12345.0.1"
        assert len(trap_varbinds) == 1

    async def test_send_trap_multiple_varbinds(self, bound_updater):
        """send_trap with multiple varbinds."""
        updater, agent = bound_updater

        vb1 = VarBind(Oid("1.3.6.1.4.1.12345.1.0"), Value.Integer(42))
        vb2 = VarBind(Oid("1.3.6.1.4.1.12345.2.0"), Value.OctetString(b"test"))
        await updater.send_trap("1.3.6.1.4.1.12345.0.1", vb1, vb2)

        trap_oid, trap_varbinds = agent.traps_sent[0]
        assert len(trap_varbinds) == 2

    async def test_send_trap_unbound_raises(self, updater):
        """send_trap raises when not bound to agent."""
        vb = VarBind(Oid("1.3.6.1"), Value.Integer(1))
        with pytest.raises(RuntimeError, match="not bound"):
            await updater.send_trap("1.3.6.1.0.1", vb)


class TestUpdaterUpdate:
    """Tests for the update method."""

    async def test_update_default_does_nothing(self, updater):
        """Default update() is a no-op."""
        await updater.update()
        assert updater._values == {}

    async def test_update_subclass(self):
        """Subclass can override update() to set values."""

        class TestUpdater(Updater):
            async def update(self):
                self.set_INTEGER("1.0", 42)
                self.set_OCTETSTRING("2.0", "hello")

        u = TestUpdater()
        await u.update()

        assert u._values["1.0"] == Value.Integer(42)
        assert u._values["2.0"] == Value.OctetString(b"hello")


class TestUpdaterOverwrite:
    """Tests for value overwriting behavior."""

    def test_overwrite_value(self, updater):
        """Setting same OID overwrites previous value."""
        updater.set_INTEGER("1.0", 42)
        updater.set_INTEGER("1.0", 100)

        assert updater._values["1.0"] == Value.Integer(100)
        assert len(updater._values) == 1

    def test_overwrite_different_type(self, updater):
        """Can overwrite with different value type."""
        updater.set_INTEGER("1.0", 42)
        updater.set_OCTETSTRING("1.0", b"now a string")

        assert updater._values["1.0"] == Value.OctetString(b"now a string")
