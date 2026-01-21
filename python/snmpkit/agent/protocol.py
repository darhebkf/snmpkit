from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from snmpkit.agent.exceptions import (
    ConnectionError,
    ProtocolError,
    RegistrationError,
    SessionError,
)
from snmpkit.core import (
    HEADER_SIZE,
    CloseReasons,
    Oid,
    PduTypes,
    VarBind,
    decode_header,
    decode_response_pdu,
    encode_close_pdu,
    encode_notify_pdu,
    encode_open_pdu,
    encode_ping_pdu,
    encode_register_pdu,
    encode_response_pdu,
    encode_unregister_pdu,
)

if TYPE_CHECKING:
    from snmpkit.agent.agent import Registration

logger = logging.getLogger("snmpkit.agent")


class Protocol:
    """AgentX protocol handler for socket communication."""

    def __init__(self, agent_id: str, socket_path: str, timeout: int) -> None:
        self._agent_id = agent_id
        self._socket_path = socket_path
        self._timeout = timeout

        self._session_id: int = 0
        self._transaction_id: int = 0
        self._packet_id: int = 0

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._recv_buf: bytes = b""

    @property
    def session_id(self) -> int:
        return self._session_id

    def _next_packet_id(self) -> int:
        self._packet_id += 1
        return self._packet_id

    def _next_transaction_id(self) -> int:
        self._transaction_id += 1
        return self._transaction_id

    async def connect(self) -> None:
        """Connect to the AgentX master agent."""
        logger.info("Connecting to %s", self._socket_path)
        self._reader, self._writer = await asyncio.open_unix_connection(self._socket_path)
        logger.info("Connected to %s", self._socket_path)

    async def disconnect(self) -> None:
        """Close the socket connection."""
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._reader = None
        self._writer = None
        self._recv_buf = b""

    async def send(self, data: bytes) -> None:
        """Send data to master agent."""
        if self._writer is None:
            raise SessionError("Not connected")
        self._writer.write(data)
        await self._writer.drain()

    async def recv_pdu(self, timeout: float = 0.1) -> tuple[object, bytes] | None:
        """Receive a complete PDU from master agent."""
        if self._reader is None:
            raise SessionError("Not connected")

        while len(self._recv_buf) < HEADER_SIZE:
            try:
                chunk = await asyncio.wait_for(self._reader.read(4096), timeout=timeout)
                if not chunk:
                    return None
                self._recv_buf += chunk
            except asyncio.TimeoutError:
                return None

        header = decode_header(self._recv_buf[:HEADER_SIZE])
        payload_len = header.payload_length

        total_len = HEADER_SIZE + payload_len
        while len(self._recv_buf) < total_len:
            chunk = await self._reader.read(total_len - len(self._recv_buf))
            if not chunk:
                return None
            self._recv_buf += chunk

        payload = self._recv_buf[HEADER_SIZE:total_len]
        self._recv_buf = self._recv_buf[total_len:]

        return header, payload

    async def open_session(self) -> None:
        """Send Open PDU and establish session."""
        pdu = encode_open_pdu(
            session_id=0,
            transaction_id=self._next_transaction_id(),
            packet_id=self._next_packet_id(),
            timeout=self._timeout,
            oid=Oid("1.3.6.1.4.1.0"),
            description=self._agent_id,
        )
        await self.send(pdu)
        logger.debug("Sent Open PDU")

        result = await self.recv_pdu(timeout=5.0)
        if result is None:
            raise ConnectionError("No response to Open PDU")

        header, payload = result
        if header.pdu_type != PduTypes.RESPONSE:
            raise ProtocolError(f"Expected Response, got type {header.pdu_type}")

        response = decode_response_pdu(payload, header.payload_length)
        if response.is_error:
            raise ConnectionError(f"Open failed with error {response.error}")

        self._session_id = header.session_id
        logger.info("Session established: session_id=%d", self._session_id)

    async def close_session(self, reason: int = CloseReasons.SHUTDOWN) -> None:
        """Send Close PDU and end session."""
        if self._session_id == 0:
            return

        pdu = encode_close_pdu(
            session_id=self._session_id,
            transaction_id=self._next_transaction_id(),
            packet_id=self._next_packet_id(),
            reason=reason,
        )
        try:
            await self.send(pdu)
            logger.debug("Sent Close PDU")
        except Exception as e:
            logger.warning("Failed to send Close PDU: %s", e)

        self._session_id = 0

    async def ping(self) -> None:
        """Send Ping PDU to verify connection."""
        pdu = encode_ping_pdu(
            session_id=self._session_id,
            transaction_id=self._next_transaction_id(),
            packet_id=self._next_packet_id(),
        )
        await self.send(pdu)
        logger.debug("Sent Ping PDU")

        result = await self.recv_pdu(timeout=5.0)
        if result is None:
            raise ConnectionError("No response to Ping PDU")

        header, payload = result
        if header.pdu_type != PduTypes.RESPONSE:
            raise ProtocolError(f"Expected Response, got type {header.pdu_type}")

    async def register_oid(self, reg: Registration) -> None:
        """Send Register PDU for an OID subtree."""
        pdu = encode_register_pdu(
            session_id=self._session_id,
            transaction_id=self._next_transaction_id(),
            packet_id=self._next_packet_id(),
            subtree=Oid(reg.oid),
            priority=reg.priority,
            timeout=self._timeout,
            context=reg.context,
        )
        await self.send(pdu)
        logger.debug("Sent Register PDU for %s", reg.oid)

        result = await self.recv_pdu(timeout=5.0)
        if result is None:
            raise RegistrationError(f"No response to Register PDU for {reg.oid}")

        header, payload = result
        if header.pdu_type != PduTypes.RESPONSE:
            raise ProtocolError(f"Expected Response, got type {header.pdu_type}")

        response = decode_response_pdu(payload, header.payload_length)
        if response.is_error:
            raise RegistrationError(f"Registration failed for {reg.oid}: error {response.error}")

        logger.info("Registered OID %s (context=%s)", reg.oid, reg.context)

    async def unregister_oid(self, oid: str, context: str | None, priority: int) -> None:
        """Send Unregister PDU for an OID subtree."""
        pdu = encode_unregister_pdu(
            session_id=self._session_id,
            transaction_id=self._next_transaction_id(),
            packet_id=self._next_packet_id(),
            subtree=Oid(oid),
            priority=priority,
            context=context,
        )
        await self.send(pdu)
        logger.debug("Sent Unregister PDU for %s", oid)

        result = await self.recv_pdu(timeout=5.0)
        if result is None:
            raise RegistrationError(f"No response to Unregister PDU for {oid}")

        header, payload = result
        if header.pdu_type != PduTypes.RESPONSE:
            raise ProtocolError(f"Expected Response, got type {header.pdu_type}")

    async def send_response(
        self,
        header: object,
        varbinds: list[VarBind],
        error: int = 0,
        index: int = 0,
    ) -> None:
        """Send Response PDU."""
        uptime = int(time.monotonic() * 100) & 0xFFFFFFFF

        pdu = encode_response_pdu(
            session_id=header.session_id,
            transaction_id=header.transaction_id,
            packet_id=header.packet_id,
            sys_uptime=uptime,
            error=error,
            index=index,
            varbinds=varbinds,
        )
        await self.send(pdu)

    async def send_notify(self, varbinds: list[VarBind]) -> None:
        """Send Notify PDU (trap)."""
        pdu = encode_notify_pdu(
            session_id=self._session_id,
            transaction_id=self._next_transaction_id(),
            packet_id=self._next_packet_id(),
            varbinds=varbinds,
        )
        await self.send(pdu)
        logger.debug("Sent Notify PDU")
