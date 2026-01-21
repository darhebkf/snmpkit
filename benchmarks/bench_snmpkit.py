#!/usr/bin/env python3
import time

from snmpkit.core import (
    Oid,
    Value,
    VarBind,
    decode_header,
    encode_response_pdu,
)

ITERATIONS = 10000


def bench_oid_parse():
    oid_str = "1.3.6.1.4.1.27108.3.1.1.1.1.2.42"
    start = time.perf_counter()
    for _ in range(ITERATIONS):
        Oid(oid_str)
    return time.perf_counter() - start


def bench_value_create():
    start = time.perf_counter()
    for _ in range(ITERATIONS):
        Value.Integer(12345)
        Value.OctetString(b"test string value")
        Value.Counter64(9999999999)
    return time.perf_counter() - start


def bench_pdu_encode():
    oid1 = Oid("1.3.6.1.2.1.1.1.0")
    oid2 = Oid("1.3.6.1.2.1.1.2.0")
    val1 = Value.Integer(42)
    val2 = Value.OctetString(b"test")
    varbinds = [VarBind(oid1, val1), VarBind(oid2, val2)]

    start = time.perf_counter()
    for _ in range(ITERATIONS):
        encode_response_pdu(
            session_id=1,
            transaction_id=100,
            packet_id=50,
            sys_uptime=0,
            error=0,
            index=0,
            varbinds=varbinds,
        )
    return time.perf_counter() - start


def bench_header_decode():
    oid1 = Oid("1.3.6.1.2.1.1.1.0")
    val1 = Value.Integer(42)
    encoded = encode_response_pdu(
        session_id=1,
        transaction_id=100,
        packet_id=50,
        sys_uptime=0,
        error=0,
        index=0,
        varbinds=[VarBind(oid1, val1)],
    )

    start = time.perf_counter()
    for _ in range(ITERATIONS):
        decode_header(encoded)
    return time.perf_counter() - start


def run_all():
    results = {}
    results["oid_parse"] = bench_oid_parse()
    results["value_create"] = bench_value_create()
    results["pdu_encode"] = bench_pdu_encode()
    results["header_decode"] = bench_header_decode()
    return results


if __name__ == "__main__":
    print(f"snmpkit benchmarks ({ITERATIONS} iterations)")
    print("-" * 40)
    results = run_all()
    for name, elapsed in results.items():
        ops_per_sec = ITERATIONS / elapsed
        print(f"{name}: {elapsed:.4f}s ({ops_per_sec:,.0f} ops/sec)")
