export type FileStatus = "added" | "modified" | "deleted" | "renamed";

export interface ChangedFile {
  path: string;
  status: FileStatus;
  /** Renamed files only. */
  oldPath?: string;
}

/** What a review needs from a repository; Git in production, a map of files in tests of single checks. */
export interface Source {
  base: string;
  head: string;
  changed: ChangedFile[];
  /** Messages of the commits of the change. */
  messages: string[];
  /** Every file of the head tree. */
  tree: string[];
  /** A file at head, or undefined. */
  readHead(path: string): string | undefined;
  /** A file at the base, or undefined. */
  readBase(path: string): string | undefined;
  /** The diff of one file with some context (whitespace and blank lines ignored on request), or "". */
  diff(path: string, context: number, ignoreSpace?: boolean): string;
}

export type Level = "error" | "warning" | "info";

/** A finding of a deterministic check. */
export interface Finding {
  rule: string;
  level: Level;
  message: string;
  file?: string;
  line?: number;
  capability?: string;
}

export interface Touched {
  capability: string;
  reasons: string[];
}

export interface NoSpec {
  reason: string;
  source: "label" | "commit" | "option";
}

export interface Evidence {
  file: string;
  line: number;
  quote: string;
}

export const KINDS = ["contradiction", "unspecified-change", "stale-spec", "adr-conflict", "missing-test"] as const;
export const SEVERITIES = ["high", "medium", "low"] as const;
export const CONFIDENCES = ["high", "medium", "low"] as const;
export const ACTIONS = ["fix-code", "revise-spec", "decide"] as const;

/** A finding of the model, as it answers (the program corrects the lines after checking the quotes). */
export interface ModelFinding {
  kind: (typeof KINDS)[number];
  severity: (typeof SEVERITIES)[number];
  confidence: (typeof CONFIDENCES)[number];
  /** A requirement name of the spec, or `ADR NNNN`. */
  requirement: string;
  spec: Evidence;
  code: Evidence;
  explanation: string;
  action: (typeof ACTIONS)[number];
}

export interface Rejected {
  requirement: string;
  reason: string;
}

export type ReviewState =
  | { state: "not-requested" }
  /** Requested, but no capability is touched by the change: the model was not contacted. */
  | { state: "nothing-to-review" }
  | { state: "unavailable"; reason: string }
  | { state: "failed"; reason: string }
  | { state: "completed"; provider: string; model: string };

export interface ReviewReport {
  status: ReviewState;
  /** Capabilities asked about, and those left out for lack of budget. */
  reviewed: string[];
  skipped: string[];
  findings: ModelFinding[];
  rejected: Rejected[];
}

export interface Report {
  base: string;
  head: string;
  changed: ChangedFile[];
  touched: Touched[];
  unmapped: string[];
  noSpec: NoSpec | null;
  /** Checks that did not run, with the reason: never read as passed. */
  skippedChecks: string[];
  findings: Finding[];
  review: ReviewReport;
  /** What makes the command exit non-zero, one line each. */
  blockers: string[];
}
