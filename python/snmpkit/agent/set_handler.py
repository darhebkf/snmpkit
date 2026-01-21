from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from snmpkit.agent.agent import Agent


class SetHandler:
    """Base class for SNMP SET operations. Override test/commit methods."""

    def __init__(self) -> None:
        self._agent: Agent | None = None
        self._base_oid: str = ""
        self._transactions: dict[str, tuple[str, Any]] = {}

    def _bind(self, agent: Agent, base_oid: str) -> None:
        """Called by Agent when registering this handler."""
        self._agent = agent
        self._base_oid = base_oid

    def _make_tid(self, session_id: int, transaction_id: int) -> str:
        return f"{session_id}_{transaction_id}"

    async def _network_test(
        self, session_id: int, transaction_id: int, oid: str, value: Any
    ) -> None:
        """Called by network layer for TestSet PDU."""
        tid = self._make_tid(session_id, transaction_id)
        self._transactions.pop(tid, None)
        await self.test(oid, value)
        self._transactions[tid] = (oid, value)

    async def _network_commit(self, session_id: int, transaction_id: int) -> None:
        """Called by network layer for CommitSet PDU."""
        tid = self._make_tid(session_id, transaction_id)
        if tid not in self._transactions:
            return
        oid, value = self._transactions[tid]
        await self.commit(oid, value)
        self._transactions.pop(tid, None)

    async def _network_undo(self, session_id: int, transaction_id: int) -> None:
        """Called by network layer for UndoSet PDU."""
        tid = self._make_tid(session_id, transaction_id)
        if tid in self._transactions:
            oid, _ = self._transactions[tid]
            await self.undo(oid)
            self._transactions.pop(tid, None)

    async def _network_cleanup(self, session_id: int, transaction_id: int) -> None:
        """Called by network layer for CleanupSet PDU."""
        tid = self._make_tid(session_id, transaction_id)
        if tid in self._transactions:
            oid, _ = self._transactions[tid]
            await self.cleanup(oid)
            self._transactions.pop(tid, None)

    # User overrides these

    async def test(self, oid: str, value: Any) -> None:
        """Validate the SET request. Raise exception to reject."""

    async def commit(self, oid: str, value: Any) -> None:
        """Apply the SET value. Called after successful test."""

    async def undo(self, oid: str) -> None:
        """Rollback the SET if commit failed elsewhere in transaction."""

    async def cleanup(self, oid: str) -> None:
        """Cleanup after transaction completes (success or failure)."""
