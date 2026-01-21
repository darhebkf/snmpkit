from __future__ import annotations

from typing import TYPE_CHECKING

from snmpkit.core import Oid, Value, VarBind

if TYPE_CHECKING:
    from snmpkit.agent.agent import Agent


class Updater:
    """Base class for OID handlers. Override update() to provide values."""

    def __init__(self) -> None:
        self._values: dict[str, Value] = {}
        self._agent: Agent | None = None
        self._base_oid: str = ""

    def _bind(self, agent: Agent, base_oid: str) -> None:
        """Called by Agent when registering this updater."""
        self._agent = agent
        self._base_oid = base_oid

    async def update(self) -> None:
        """Override to set values. Called periodically by the agent."""

    def get_varbinds(self) -> list[VarBind]:
        """Return all values as VarBinds for responding to requests."""
        result = []
        for oid_str, value in self._values.items():
            full_oid = f"{self._base_oid}.{oid_str}" if self._base_oid else oid_str
            result.append(VarBind(Oid(full_oid), value))
        return result

    def get_value(self, oid: str) -> Value | None:
        """Get value for a specific OID suffix."""
        return self._values.get(oid)

    def clear(self) -> None:
        """Clear all stored values."""
        self._values.clear()

    # Value setters

    def set_INTEGER(self, oid: str, value: int) -> None:
        self._values[oid] = Value.Integer(value)

    def set_OCTETSTRING(self, oid: str, value: str | bytes) -> None:
        if isinstance(value, str):
            value = value.encode("utf-8")
        self._values[oid] = Value.OctetString(value)

    def set_OBJECTIDENTIFIER(self, oid: str, value: str) -> None:
        self._values[oid] = Value.ObjectIdentifier(Oid(value))

    def set_IPADDRESS(self, oid: str, value: str) -> None:
        parts = [int(p) for p in value.split(".")]
        if len(parts) != 4:
            raise ValueError(f"Invalid IP address: {value}")
        self._values[oid] = Value.IpAddress(parts[0], parts[1], parts[2], parts[3])

    def set_COUNTER32(self, oid: str, value: int) -> None:
        self._values[oid] = Value.Counter32(value)

    def set_GAUGE32(self, oid: str, value: int) -> None:
        self._values[oid] = Value.Gauge32(value)

    def set_TIMETICKS(self, oid: str, value: int) -> None:
        self._values[oid] = Value.TimeTicks(value)

    def set_OPAQUE(self, oid: str, value: bytes) -> None:
        self._values[oid] = Value.Opaque(value)

    def set_COUNTER64(self, oid: str, value: int) -> None:
        self._values[oid] = Value.Counter64(value)

    # Trap sending

    async def send_trap(self, oid: str, *varbinds: VarBind) -> None:
        """Send a trap/notification to the master agent."""
        if self._agent is None:
            raise RuntimeError("Updater not bound to an agent")
        await self._agent._send_trap(oid, list(varbinds))
