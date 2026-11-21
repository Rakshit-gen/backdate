// Shapes returned by the backdate API (backdate/api/views.py).

export type Span = { from: string; to: string | null };

export type HistoryRow = Span & { value: unknown; tx_from: number; tx_to: number | null };
export type History = { entity: string; attribute: string; rows: HistoryRow[] };

export type Status = "pending" | "fresh" | "stale" | "failed";

export type Computation = {
  id: number;
  derivation: string;
  key: string;
  status: Status;
  result: Record<string, unknown> | null;
  result_version: number | null;
  result_seq: number;
  stale_since_version: number | null;
  attempts: number;
  last_error: string;
  lease: { owner: string; token: number; expires_at: string | null };
  updated_at: string;
};

export type Read = Span & { entity: string; attribute: string };

export type Graph = {
  version: number;
  computations: (Computation & { reads: Read[] })[];
  edges: { source: number; reader: number; observed_seq: number }[];
  truncated: boolean;
};

export type Restatement = {
  computation: { id: number; derivation: string; key: string };
  seq: number;
  from_version: number | null;
  to_version: number;
  previous: Record<string, unknown> | null;
  current: Record<string, unknown>;
  delta: Record<string, number> | number | null;
  created_at: string;
};

export type Changeset = {
  version: number;
  recorded_at: string;
  actor: string;
  reason: string;
  changes: (Span & { entity: string; attribute: string })[];
};

export type Clock = { version: number; computations: Record<Status, number> };

export type WriteResult = {
  version: number;
  noop: boolean;
  invalidated: number;
  changes: (Span & { entity: string; attribute: string })[];
};

/** Everything the page renders for one employee. */
export type Scene = {
  employee: number;
  clock: Clock;
  salary: History;
  fte: History;
  state: History;
  graph: Graph;
  computations: Computation[];
  restatements: Restatement[];
  changesets: Changeset[];
};

export type Source =
  | { kind: "live"; scene: Scene }
  | { kind: "recording"; scene: Scene; recordedAt: string; note: string; problem?: string };
