import { globToRegExp } from "./glob.ts";
import type { Source } from "./types.ts";

export interface Requirement {
  name: string;
  /** 1-based line of the `### Requirement:` heading. */
  line: number;
  /** Lines of the requirement, from its heading to the next one. */
  end: number;
  scenarios: Array<{ name: string; line: number }>;
}

/** Requirements and their scenarios, by their headings. */
export function parseRequirements(markdown: string): Requirement[] {
  const lines = markdown.split("\n");
  const found: Requirement[] = [];
  lines.forEach((text, i) => {
    const requirement = /^###\s+Requirement:\s*(.+?)\s*$/.exec(text);
    if (requirement) {
      const last = found.at(-1);
      if (last) last.end = i;
      found.push({ name: requirement[1]!, line: i + 1, end: lines.length, scenarios: [] });
      return;
    }
    const scenario = /^####\s+Scenario:\s*(.+?)\s*$/.exec(text);
    if (scenario) found.at(-1)?.scenarios.push({ name: scenario[1]!, line: i + 1 });
    else if (/^##\s/.test(text)) {
      const last = found.at(-1);
      if (last && last.end === lines.length) last.end = i;
    }
  });
  return found;
}

export interface CodeMap {
  [capability: string]: { code: string[]; tests: string[] };
}

export const CODE_MAP_PATH = "openspec/code-map.json";

/** `openspec/code-map.json`: `{ "capabilities": { "<name>": { "code": [globs], "tests": [globs] } } }`. */
export function readCodeMap(source: Source): { map: CodeMap; error?: string } {
  const text = source.readHead(CODE_MAP_PATH);
  if (text === undefined) return { map: {}, error: `${CODE_MAP_PATH} is missing` };
  try {
    const parsed = JSON.parse(text) as { capabilities?: Record<string, { code?: string[]; tests?: string[] }> };
    const map: CodeMap = {};
    for (const [name, entry] of Object.entries(parsed.capabilities ?? {}))
      map[name] = { code: entry.code ?? [], tests: entry.tests ?? [] };
    return { map };
  } catch (e) {
    return { map: {}, error: `${CODE_MAP_PATH} is not valid JSON: ${(e as Error).message}` };
  }
}

/** The capabilities whose code (or tests) globs match a path. */
export function capabilitiesOf(map: CodeMap, path: string, kind: "code" | "tests"): string[] {
  return Object.entries(map)
    .filter(([, entry]) => entry[kind].some((g) => globToRegExp(g).test(path)))
    .map(([name]) => name);
}

export const specPath = (capability: string) => `openspec/specs/${capability}/spec.md`;

/** The capabilities that exist: a folder under openspec/specs/. */
export function capabilitiesOfTree(tree: string[]): string[] {
  return [
    ...new Set(tree.map((p) => /^openspec\/specs\/([^/]+)\/spec\.md$/.exec(p)?.[1]).filter((c): c is string => !!c)),
  ].sort();
}

export interface Proposal {
  id: string;
  /** Capabilities with a delta spec in the proposal. */
  capabilities: string[];
}

/** Open proposals (not archived) and the capabilities of their delta specs. */
export function openProposals(tree: string[]): Proposal[] {
  const proposals = new Map<string, Set<string>>();
  for (const path of tree) {
    const m = /^openspec\/changes\/([^/]+)\//.exec(path);
    if (!m || m[1] === "archive") continue;
    const set = proposals.get(m[1]!) ?? proposals.set(m[1]!, new Set()).get(m[1]!)!;
    const delta = /^openspec\/changes\/[^/]+\/specs\/([^/]+)\/spec\.md$/.exec(path);
    if (delta) set.add(delta[1]!);
  }
  return [...proposals].map(([id, set]) => ({ id, capabilities: [...set].sort() }));
}

/** ADR numbers cited as `ADR 0044` or as a path `docs/adr/0044-...`. */
export function citedRecords(text: string): Array<{ number: string; line: number }> {
  const found: Array<{ number: string; line: number }> = [];
  text.split("\n").forEach((line, i) => {
    for (const m of line.matchAll(/\bADRs?\s+(\d{4})\b|docs\/adr\/(\d{4})-/g))
      found.push({ number: (m[1] ?? m[2])!, line: i + 1 });
  });
  return found;
}

export const adrFile = (tree: string[], number: string): string | undefined =>
  tree.find((p) => new RegExp(`^docs/adr/${number}-[^/]+\\.md$`).test(p));
