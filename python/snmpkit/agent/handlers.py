from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from snmpkit.core import (
    Oid,
    Value,
    VarBind,
    decode_get_pdu,
    decode_getbulk_pdu,
    decode_testset_pdu,
)

if TYPE_CHECKING:
    from snmpkit.agent.protocol import Protocol
    from snmpkit.agent.set_handler import SetHandler

logger = logging.getLogger("snmpkit.agent")

NOT_WRITABLE = 17
WRONG_VALUE = 10


class DataStore:
    """OID value storage with lexicographic ordering."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, VarBind]] = {}
        self._data_idx: dict[str, list[str]] = {}

    def update(self, oid: str, context: str | None, varbinds: list[VarBind]) -> None:
        """Update stored data for an OID subtree."""
        ctx_key = context or ""
        if ctx_key not in self._data:
            self._data[ctx_key] = {}
            self._data_idx[ctx_key] = []

        prefix = oid + "."
        to_delete = [k for k in self._data[ctx_key] if k.startswith(prefix) or k == oid]
        for k in to_delete:
            del self._data[ctx_key][k]

        for vb in varbinds:
            full_oid = str(vb.oid)
            self._data[ctx_key][full_oid] = vb

        self._data_idx[ctx_key] = sorted(
            self._data[ctx_key].keys(),
            key=lambda k: tuple(int(p) for p in k.split(".")),
        )

    def get(self, oid: str, context: str | None) -> VarBind | None:
        """Get exact value for an OID."""
        ctx_key = context or ""
        return self._data.get(ctx_key, {}).get(oid)

    def get_next(self, oid: str, end_oid: str, context: str | None) -> str | None:
        """Get next OID in lexicographic order."""
        ctx_key = context or ""
        ctx_data = self._data.get(ctx_key, {})
        ctx_idx = self._data_idx.get(ctx_key, [])

        if not ctx_idx:
            return None

        if oid in ctx_data:
            idx = ctx_idx.index(oid)
            if idx < len(ctx_idx) - 1:
                next_oid = ctx_idx[idx + 1]
                if self._oid_le(next_oid, end_oid):
                    return next_oid
            return None

        oid_tuple = tuple(int(p) for p in oid.split("."))
        end_tuple = tuple(int(p) for p in end_oid.split(".")) if end_oid else None

        for candidate in ctx_idx:
            candidate_tuple = tuple(int(p) for p in candidate.split("."))
            if candidate_tuple > oid_tuple:
                if end_tuple is None or candidate_tuple <= end_tuple:
                    return candidate
                break

        return None

    def _oid_le(self, oid1: str, oid2: str) -> bool:
        """Check if oid1 <= oid2 lexicographically."""
        if not oid2:
            return True
        t1 = tuple(int(p) for p in oid1.split("."))
        t2 = tuple(int(p) for p in oid2.split("."))
        return t1 <= t2

    def init_context(self, context: str | None) -> None:
        """Initialize data store for a context."""
        ctx_key = context or ""
        if ctx_key not in self._data:
            self._data[ctx_key] = {}
            self._data_idx[ctx_key] = []


class RequestHandler:
    """Handles incoming SNMP requests."""

    def __init__(
        self,
        protocol: Protocol,
        data_store: DataStore,
        set_handlers: dict[str, SetHandler],
    ) -> None:
        self._protocol = protocol
        self._data = data_store
        self._set_handlers = set_handlers

    async def handle_get(self, header: object, payload: bytes) -> None:
        """Handle GET request."""
        get_pdu = decode_get_pdu(payload, header.payload_length)
        varbinds = []

        for start_oid, end_oid, include in get_pdu.ranges:
            oid_str = str(start_oid)
            vb = self._data.get(oid_str, None)
            if vb:
                varbinds.append(vb)
            else:
                varbinds.append(VarBind(start_oid, Value.NoSuchObject()))

        await self._protocol.send_response(header, varbinds)

    async def handle_getnext(self, header: object, payload: bytes) -> None:
        """Handle GETNEXT request."""
        get_pdu = decode_get_pdu(payload, header.payload_length)
        varbinds = []

        for start_oid, end_oid, include in get_pdu.ranges:
            oid_str = str(start_oid)
            end_str = str(end_oid) if end_oid else ""

            next_oid = self._data.get_next(oid_str, end_str, None)
            if next_oid:
                vb = self._data.get(next_oid, None)
                if vb:
                    varbinds.append(vb)
                else:
                    varbinds.append(VarBind(Oid(oid_str), Value.EndOfMibView()))
            else:
                varbinds.append(VarBind(Oid(oid_str), Value.EndOfMibView()))

        await self._protocol.send_response(header, varbinds)

    async def handle_getbulk(self, header: object, payload: bytes) -> None:
        """Handle GETBULK request."""
        bulk_pdu = decode_getbulk_pdu(payload, header.payload_length)
        varbinds = []

        non_repeaters = bulk_pdu.non_repeaters
        max_reps = bulk_pdu.max_repetitions

        for i, (start_oid, end_oid, include) in enumerate(bulk_pdu.ranges):
            oid_str = str(start_oid)
            end_str = str(end_oid) if end_oid else ""

            if i < non_repeaters:
                next_oid = self._data.get_next(oid_str, end_str, None)
                if next_oid:
                    vb = self._data.get(next_oid, None)
                    if vb:
                        varbinds.append(vb)
                    else:
                        varbinds.append(VarBind(Oid(oid_str), Value.EndOfMibView()))
                else:
                    varbinds.append(VarBind(Oid(oid_str), Value.EndOfMibView()))
            else:
                current = oid_str
                for _ in range(max_reps):
                    next_oid = self._data.get_next(current, end_str, None)
                    if next_oid:
                        vb = self._data.get(next_oid, None)
                        if vb:
                            varbinds.append(vb)
                            current = next_oid
                        else:
                            varbinds.append(VarBind(Oid(current), Value.EndOfMibView()))
                            break
                    else:
                        varbinds.append(VarBind(Oid(current), Value.EndOfMibView()))
                        break

        await self._protocol.send_response(header, varbinds)

    async def handle_testset(self, header: object, payload: bytes) -> None:
        """Handle TESTSET request."""
        testset_pdu = decode_testset_pdu(payload, header.payload_length)
        error = 0
        error_idx = 0

        for i, vb in enumerate(testset_pdu.varbinds, 1):
            oid_str = str(vb.oid)
            handler = self._find_set_handler(oid_str)
            if handler is None:
                error = NOT_WRITABLE
                error_idx = i
                break

            try:
                await handler._network_test(
                    header.session_id, header.transaction_id, oid_str, vb.value
                )
            except Exception as e:
                logger.warning("TestSet failed for %s: %s", oid_str, e)
                error = WRONG_VALUE
                error_idx = i
                break

        await self._protocol.send_response(header, [], error=error, index=error_idx)

    async def handle_commitset(self, header: object) -> None:
        """Handle COMMITSET request."""
        for handler in self._set_handlers.values():
            await handler._network_commit(header.session_id, header.transaction_id)
        await self._protocol.send_response(header, [])

    async def handle_undoset(self, header: object) -> None:
        """Handle UNDOSET request."""
        for handler in self._set_handlers.values():
            await handler._network_undo(header.session_id, header.transaction_id)
        await self._protocol.send_response(header, [])

    async def handle_cleanupset(self, header: object) -> None:
        """Handle CLEANUPSET request."""
        for handler in self._set_handlers.values():
            await handler._network_cleanup(header.session_id, header.transaction_id)
        await self._protocol.send_response(header, [])

    def _find_set_handler(self, oid: str) -> SetHandler | None:
        """Find the SetHandler for an OID."""
        for key, handler in self._set_handlers.items():
            handler_oid = key.split(":")[0]
            if oid.startswith(handler_oid):
                return handler
        return None
