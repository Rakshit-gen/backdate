import type { Metadata } from "next";
import { PageHead } from "@/components/PageHead";

export const metadata: Metadata = { title: "Benchmarks" };

// Copied from docs/benchmarks.md (bench/run.py, 2026-11-21). These are recorded numbers, not live ones.

type Row = { label: string; value: number; shown: string; accent?: boolean };

function Bars({ rows, caption }: { rows: Row[]; caption: string }) {
  const max = Math.max(...rows.map((r) => r.value));
  return (
    <table className="bars">
      <caption className="muted">{caption}</caption>
      <tbody>
        {rows.map((r) => (
          <tr key={r.label}>
            <th scope="row">{r.label}</th>
            <td>
              <span className={`bar${r.accent ? " accent" : ""}`} style={{ width: `${Math.max(0.4, (r.value / max) * 100)}%` }} />
            </td>
            <td className="num">{r.shown}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function Page() {
  return (
    <div className="page">
      <PageHead title="Benchmarks">
        <p>
          From <code>bench/run.py</code> on one Apple Silicon Mac with Postgres 18 on the same machine:
          200 employees, 12 months, 4,800 results. Compare the rows with each other, not with
          production numbers from elsewhere.
        </p>
      </PageHead>

      <section className="block split">
        <div>
          <h2>Recompute only what read the change</h2>
          <p className="muted">
            One raise effective 1 July for one employee, then wait until every result is fresh again,
            with 4 worker processes. Naive marks everything stale, which is what you do without
            read sets.
          </p>
        </div>
        <div>
          <Bars
            caption="Results recomputed"
            rows={[
              { label: "Targeted", value: 12, shown: "12", accent: true },
              { label: "Naive", value: 4800, shown: "4,800" },
            ]}
          />
          <Bars
            caption="Time until consistent"
            rows={[
              { label: "Targeted", value: 0.67, shown: "0.67 s", accent: true },
              { label: "Naive", value: 8.82, shown: "8.82 s" },
            ]}
          />
          <p className="muted small">
            The 12 are July to December, gross and withholding. About 0.39 s of the 0.67 s is starting
            the worker processes, not computing.
          </p>
        </div>
      </section>

      <section className="block split">
        <div>
          <h2>Backdated write latency</h2>
          <p className="muted">
            300 single-op raises against a fully computed tenant. Each one takes the clock lock,
            diffs, writes fact rows and change ranges, and runs the invalidation join. On average a
            write marked 10.5 results stale.
          </p>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th className="num">p50</th>
                <th className="num">p95</th>
                <th className="num">p99</th>
                <th className="num">mean</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="num">4.33 ms</td>
                <td className="num">4.84 ms</td>
                <td className="num">7.58 ms</td>
                <td className="num">4.41 ms</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="block split">
        <div>
          <h2>Recompute throughput</h2>
          <p className="muted">
            Draining all 4,800 results from empty. 1 to 2 processes is about 2x. 2 to 4 is worse, and
            I haven&rsquo;t profiled why. The share lock on the single tenant clock during saves is
            the first suspect.
          </p>
        </div>
        <Bars
          caption="Results per second"
          rows={[
            { label: "1 worker", value: 177, shown: "177" },
            { label: "2 workers", value: 375, shown: "375" },
            { label: "4 workers", value: 525, shown: "525" },
          ]}
        />
      </section>

      <section className="block split">
        <div>
          <h2>The cost of one clock per tenant</h2>
          <p className="muted">
            8 threads, 50 writes each. In one tenant every write queues on the same clock row. Spread
            over 8 tenants they don&rsquo;t. It isn&rsquo;t 8x because the threads share one Python
            process and one machine.
          </p>
        </div>
        <div>
          <Bars
            caption="Writes per second"
            rows={[
              { label: "1 tenant", value: 349, shown: "349" },
              { label: "8 tenants", value: 556, shown: "556" },
            ]}
          />
          <p className="muted small">p99 latency: 41.21 ms in one tenant, 21.16 ms across eight.</p>
        </div>
      </section>

      <section className="block split">
        <div>
          <h2>Recovering from a killed worker</h2>
          <p className="muted">
            <code>SIGKILL</code> a worker mid-compute with a 3 second lease, then time until another
            worker has redone its job.
          </p>
        </div>
        <p className="figure">
          3.01 s <span className="muted">with a 3 s lease. Recovery time is the lease length, as designed.</span>
        </p>
      </section>

      <section className="block">
        <p className="muted">
          Not measured yet: more than one machine, a network between app and database, pgbouncer,
          long histories, and latency through gunicorn. The full tables and caveats are in{" "}
          <code>docs/benchmarks.md</code>.
        </p>
      </section>
    </div>
  );
}
