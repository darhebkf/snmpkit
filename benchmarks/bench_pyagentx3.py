#!/usr/bin/env python3
import time

import pyagentx3
from pyagentx3.pdu import PDU

ITERATIONS = 10000


def bench_oid_encode():
    pdu = PDU()
    oid = "1.3.6.1.4.1.27108.3.1.1.1.1.2.42"
    start = time.perf_counter()
    for _ in range(ITERATIONS):
        pdu.encode_oid(oid)
    return time.perf_counter() - start


def bench_value_encode():
    pdu = PDU()
    oid = "1.3.6.1.4.1.27108.3.1.1.1.1.2.42"
    start = time.perf_counter()
    for _ in range(ITERATIONS):
        pdu.encode_value(pyagentx3.TYPE_INTEGER, oid, 12345)
        pdu.encode_value(pyagentx3.TYPE_OCTETSTRING, oid, "test string value")
        pdu.encode_value(pyagentx3.TYPE_COUNTER64, oid, 9999999999)
    return time.perf_counter() - start


def bench_pdu_encode():
    start = time.perf_counter()
    for _ in range(ITERATIONS):
        pdu = PDU(pyagentx3.AGENTX_RESPONSE_PDU)
        pdu.session_id = 1
        pdu.transaction_id = 100
        pdu.packet_id = 50
        pdu.values = [
            {"type": pyagentx3.TYPE_INTEGER, "name": "1.3.6.1.2.1.1.1.0", "value": 42},
            {"type": pyagentx3.TYPE_OCTETSTRING, "name": "1.3.6.1.2.1.1.2.0", "value": "test"},
        ]
        pdu.encode()
    return time.perf_counter() - start


def bench_header_decode():
    pdu = PDU(pyagentx3.AGENTX_RESPONSE_PDU)
    pdu.session_id = 1
    pdu.transaction_id = 100
    pdu.packet_id = 50
    pdu.values = []
    encoded = pdu.encode()

    start = time.perf_counter()
    for _ in range(ITERATIONS):
        PDU.decode_header(encoded)
    return time.perf_counter() - start


def run_all():
    results = {}
    results["oid_encode"] = bench_oid_encode()
    results["value_encode"] = bench_value_encode()
    results["pdu_encode"] = bench_pdu_encode()
    results["header_decode"] = bench_header_decode()
    return results


if __name__ == "__main__":
    print(f"pyagentx3 benchmarks ({ITERATIONS} iterations)")
    print("-" * 40)
    results = run_all()
    for name, elapsed in results.items():
        ops_per_sec = ITERATIONS / elapsed
        print(f"{name}: {elapsed:.4f}s ({ops_per_sec:,.0f} ops/sec)")
