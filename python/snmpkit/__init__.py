"""snmpkit: High-performance SNMP toolkit with Rust core."""

from typing import Coroutine, TypeVar

import uvloop

from snmpkit.core import __version__

T = TypeVar("T")


def run(coro: Coroutine[None, None, T]) -> T:
    """Run an async function with uvloop.

    This is the recommended entry point for async applications.
    It replaces asyncio.run() and ensures uvloop is used.

    Example:
        async def main():
            agent = Agent()
            await agent.start()

        snmpkit.run(main())
    """
    return uvloop.run(coro)


__all__ = ["__version__", "run"]
