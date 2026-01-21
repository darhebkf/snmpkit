"use client";

interface BenchmarkData {
  label: string;
  pyagentx3: number;
  snmpkit: number;
}

function formatNumber(n: number): string {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
  if (n >= 1000) return (n / 1000).toFixed(0) + "k";
  return n.toString();
}

export function BenchmarkChart({ data, title }: { data: BenchmarkData; title?: string }) {
  const max = Math.max(data.pyagentx3, data.snmpkit);
  const pyagentx3Width = (data.pyagentx3 / max) * 100;
  const snmpkitWidth = (data.snmpkit / max) * 100;
  const speedup = (data.snmpkit / data.pyagentx3).toFixed(1);

  return (
    <div className="mb-6">
      {title && <h4 className="text-sm font-medium mb-2">{title}</h4>}
      <div className="space-y-2">
        <div className="flex items-center gap-3">
          <span className="text-xs w-20 text-right text-neutral-500">snmpkit</span>
          <div className="flex-1 h-6 bg-neutral-100 dark:bg-neutral-800 rounded overflow-hidden">
            <div
              className="h-full bg-green-600 rounded"
              style={{ width: `${snmpkitWidth}%` }}
            />
          </div>
          <span className="text-xs w-16 text-neutral-600 dark:text-neutral-400">
            {formatNumber(data.snmpkit)}/s
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs w-20 text-right text-neutral-400">pyagentx3</span>
          <div className="flex-1 h-6 bg-neutral-100 dark:bg-neutral-800 rounded overflow-hidden">
            <div
              className="h-full bg-neutral-300 dark:bg-neutral-600 rounded"
              style={{ width: `${pyagentx3Width}%` }}
            />
          </div>
          <span className="text-xs w-16 text-neutral-400">
            {formatNumber(data.pyagentx3)}/s
          </span>
        </div>
      </div>
      <p className="text-xs text-neutral-500 mt-1">
        {parseFloat(speedup) > 1 ? `${speedup}x faster` : parseFloat(speedup) < 1 ? `${(1/parseFloat(speedup)).toFixed(1)}x slower` : "same"}
      </p>
    </div>
  );
}

export function AgentBenchmarks() {
  const benchmarks: BenchmarkData[] = [
    { label: "OID Parse", pyagentx3: 216030, snmpkit: 318276 },
    { label: "Value Create", pyagentx3: 52148, snmpkit: 332316 },
    { label: "PDU Encode", pyagentx3: 17007, snmpkit: 196046 },
    { label: "Header Decode", pyagentx3: 1034158, snmpkit: 967520 },
  ];

  return (
    <div className="my-6">
      <div className="flex items-center gap-4 mb-4 text-xs">
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 bg-green-600 rounded" />
          <span>snmpkit (Rust)</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 bg-neutral-300 dark:bg-neutral-600 rounded" />
          <span>pyagentx3 (Python)</span>
        </div>
      </div>
      {benchmarks.map((b) => (
        <BenchmarkChart key={b.label} data={b} title={b.label} />
      ))}
      <p className="text-xs text-neutral-500 mt-4">
        10,000 iterations per benchmark. Higher is better.
      </p>
    </div>
  );
}
