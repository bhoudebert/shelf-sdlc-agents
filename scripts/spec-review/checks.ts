import { testTitles } from "./context.ts";
import { globToRegExp } from "./glob.ts";
import {
  adrFile,
  capabilitiesOf,
  capabilitiesOfTree,
  CODE_MAP_PATH,
  citedRecords,
  openProposals,
  readCodeMap,
  specPath,
  type CodeMap,
} from "./specs.ts";
import type { ChangedFile, Finding, NoSpec, Source, Touched } from "./types.ts";

const isCode = (path: string) => path.startsWith("src/");
const isTest = (path: string) => path.startsWith("test/");
const proposalOf = (path: string) => {
  const id = /^openspec\/changes\/([^/]+)\//.exec(path)?.[1];
  return id && id !== "archive" ? id : undefined;
};

/** The reason a change has no behaviour change, from the option, or a `No-Spec: <reason>` line of a commit. */
export function findNoSpec(source: Source, option?: NoSpec, commitLines = true): NoSpec | null {
  if (option) return option;
  if (!commitLines) return null;
  for (const message of source.messages) {
    const reason = /^No-Spec:\s*(\S.*)$/im.exec(message)?.[1]?.trim();
    if (reason) return { reason, source: "commit" };
  }
  return null;
}

export interface CheckResult {
  findings: Finding[];
  touched: Touched[];
  unmapped: string[];
  noSpec: NoSpec | null;
  map: CodeMap;
}

export function runChecks(source: Source, option?: NoSpec, options: { commitLines?: boolean } = {}): CheckResult {
  const findings: Finding[] = [];
  const touched = new Map<string, string[]>();
  const touch = (capability: string, reason: string) => {
    const reasons = touched.get(capability) ?? touched.set(capability, []).get(capability)!;
    if (!reasons.includes(reason)) reasons.push(reason);
  };

  const { map, error } = readCodeMap(source);
  if (error)
    findings.push({
      rule: "code-map",
      level: "warning",
      message: `${error}: code files cannot be tied to a capability.`,
      file: CODE_MAP_PATH,
    });
  const known = capabilitiesOfTree(source.tree);

  // Spec evidence: a changed spec, or a changed file of an open proposal that names the capability.
  const proposals = openProposals(source.tree);
  const evidence = new Set<string>();
  const whitespaceOnly = new Set<string>();
  let anyEvidence = false;
  for (const file of source.changed) {
    const spec = /^openspec\/specs\/([^/]+)\/spec\.md$/.exec(file.path)?.[1];
    if (spec && !isMeaningful(source, file)) {
      whitespaceOnly.add(spec);
      touch(spec, `${specPath(spec)} changed (whitespace only)`);
    } else if (spec) {
      evidence.add(spec);
      anyEvidence = true;
      touch(spec, `${specPath(spec)} changed`);
    }
    const id = proposalOf(file.path);
    if (id) {
      anyEvidence = true;
      for (const c of proposals.find((p) => p.id === id)?.capabilities ?? []) {
        evidence.add(c);
        touch(c, `proposal ${id} changed`);
      }
    }
  }

  const noSpec = findNoSpec(source, option, options.commitLines);
  const unmapped: string[] = [];
  const newTests = newTestTitles(source);
  const docsChanged = source.changed.some((f) => f.path.startsWith("docs/"));
  for (const file of source.changed) {
    const paths = [file.path, ...(file.oldPath ? [file.oldPath] : [])];
    for (const path of paths) {
      if (isTest(path) || path.startsWith("evals/"))
        for (const c of capabilitiesOf(map, path, "tests")) touch(c, `${path} (tests)`);
    }
    if (!isCode(file.path) && !(file.oldPath && isCode(file.oldPath))) continue;
    const capabilities = [...new Set(paths.flatMap((p) => capabilitiesOf(map, p, "code")))];
    capabilities.forEach((c) => touch(c, `${file.path} (code map)`));
    if (capabilities.length === 0) {
      unmapped.push(file.path);
      findings.push({
        rule: "unmapped-file",
        level: "warning",
        message: `${file.path} is in no entry of ${CODE_MAP_PATH}: add it, so the spec it belongs to can be found.`,
        file: file.path,
      });
    }
    const covered = capabilities.length === 0 ? anyEvidence : capabilities.some((c) => evidence.has(c));
    if (covered) continue;
    const where = capabilities.length ? `the spec of ${capabilities.join(" or ")}` : "a spec or an open proposal";
    const touchedForShow = capabilities.some((c) => whitespaceOnly.has(c));
    findings.push({
      rule: "code-without-spec",
      level: noSpec ? "info" : "error",
      message: noSpec
        ? `${file.path} changes with no spec change, accepted: no behaviour change (${noSpec.reason}).`
        : `${file.path} changes but ${where} does not${docsChanged ? " (a change under docs/ is not a spec change)" : ""}${touchedForShow ? " (the spec was edited in whitespace only)" : ""}. Update the requirement, or state that the behaviour is unchanged: the \`no-spec\` label, or a \`No-Spec: <reason>\` line in a commit.`,
      file: file.path,
      capability: capabilities.join(", ") || undefined,
    });
    if (noSpec && file.status !== "deleted") {
      const reasons = suspicions(source, file.path, newTests);
      if (reasons.length)
        findings.push({
          rule: "no-spec-suspect",
          level: "warning",
          message: `${file.path} is justified as having no behaviour change (${noSpec.reason}), but ${reasons.join(" and ")}. Check that the behaviour is really unchanged.`,
          file: file.path,
          capability: capabilities.join(", ") || undefined,
        });
    }
  }

  findings.push(...codeMapFindings(source, map, known));
  findings.push(
    ...referenceFindings(
      source,
      source.changed.filter((f) => f.status !== "deleted").map((f) => f.path),
    ),
  );

  return {
    findings,
    touched: [...touched]
      .map(([capability, reasons]) => ({ capability, reasons }))
      .sort((a, b) => a.capability.localeCompare(b.capability)),
    unmapped,
    noSpec,
    map,
  };
}

/** A map that names a capability that has no spec, or a pattern that matches no file, has fallen behind. */
function codeMapFindings(source: Source, map: CodeMap, known: string[]): Finding[] {
  const findings: Finding[] = [];
  for (const [capability, entry] of Object.entries(map)) {
    if (!known.includes(capability))
      findings.push({
        rule: "code-map",
        level: "warning",
        message: `${CODE_MAP_PATH} names the capability "${capability}", which has no spec.`,
        file: CODE_MAP_PATH,
      });
    for (const glob of [...entry.code, ...entry.tests]) {
      const re = globToRegExp(glob);
      if (!source.tree.some((p) => re.test(p)))
        findings.push({
          rule: "code-map",
          level: "warning",
          message: `${CODE_MAP_PATH}: "${glob}" (${capability}) matches no file.`,
          file: CODE_MAP_PATH,
        });
    }
  }
  return findings;
}

const referencing = (path: string) =>
  path.endsWith(".md") &&
  (path.startsWith("openspec/") || path.startsWith("docs/")) &&
  !path.startsWith("docs/guide/.vitepress/") &&
  !path.startsWith("openspec/changes/archive/");

/** In some documents: records and spec paths that do not exist. */
function referenceFindings(source: Source, paths: string[]): Finding[] {
  const findings: Finding[] = [];
  const has = (prefix: string) => source.tree.some((p) => p.startsWith(prefix));
  for (const file of paths.filter(referencing).map((path) => ({ path }))) {
    const text = source.readHead(file.path);
    if (text === undefined) continue;
    const reported = new Set<string>();
    for (const { number, line } of citedRecords(text)) {
      if (adrFile(source.tree, number) || reported.has(`adr${number}`)) continue;
      reported.add(`adr${number}`);
      findings.push({
        rule: "broken-reference",
        level: "error",
        message: `ADR ${number} does not exist in docs/adr/.`,
        file: file.path,
        line,
      });
    }
    text.split("\n").forEach((content, i) => {
      for (const m of content.matchAll(/openspec\/(specs|changes)\/([a-z0-9][a-z0-9-]*)/g)) {
        if (m[2] === "archive") continue;
        const path = `openspec/${m[1]}/${m[2]}`;
        if (has(`${path}/`) || reported.has(path)) continue;
        reported.add(path);
        findings.push({
          rule: "broken-reference",
          level: "error",
          message: `${path} does not exist.`,
          file: file.path,
          line: i + 1,
        });
      }
    });
  }
  return findings;
}

/**
 * The checks that do not need a change: every document, and the code map against the tree. For cleaning up what earlier
 * changes left; "code without a spec change" is a property of a change, so it is not here.
 */
export function runAudit(source: Source): Finding[] {
  const findings: Finding[] = [];
  const { map, error } = readCodeMap(source);
  if (error) findings.push({ rule: "code-map", level: "warning", message: `${error}.`, file: CODE_MAP_PATH });
  const known = capabilitiesOfTree(source.tree);
  findings.push(...codeMapFindings(source, map, known));
  for (const capability of known) {
    if (!map[capability])
      findings.push({
        rule: "code-map",
        level: "warning",
        message: `The spec "${capability}" is in no entry of ${CODE_MAP_PATH}: a change to its code cannot be tied to it.`,
        file: specPath(capability),
      });
  }
  for (const path of source.tree.filter((p) => p.startsWith("src/") && p.endsWith(".ts"))) {
    if (capabilitiesOf(map, path, "code").length === 0)
      findings.push({
        rule: "unmapped-file",
        level: "warning",
        message: `${path} is in no entry of ${CODE_MAP_PATH}.`,
        file: path,
      });
  }
  findings.push(...referenceFindings(source, source.tree));
  return findings;
}

/** A spec file whose change is more than whitespace and blank lines (an added or deleted file always is). */
function isMeaningful(source: Source, file: ChangedFile): boolean {
  if (file.status !== "modified") return true;
  return /^[+-](?![+-])/m.test(source.diff(file.path, 0, true));
}

/** Titles of tests the change adds: a refactor leaves the tests as they are. */
function newTestTitles(source: Source): string[] {
  const titles: string[] = [];
  for (const file of source.changed) {
    if (!isTest(file.path) || file.status === "deleted" || !/\.test\.ts$/.test(file.path)) continue;
    const before = new Set(testTitles(source.readBase(file.oldPath ?? file.path) ?? ""));
    for (const title of testTitles(source.readHead(file.path) ?? "")) if (!before.has(title)) titles.push(title);
  }
  return titles;
}

const NUMBER = /(?<![\w.])\d+(?:\.\d+)?(?![\w.])/g;
const STRING = /"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\\n]|\\.)*`/g;

/** Numbers and strings of the added or removed lines of a diff, comments and imports left out. */
export function literalsOf(diff: string, sign: "+" | "-"): string[] {
  const out: string[] = [];
  for (const line of diff.split("\n")) {
    if (line[0] !== sign || line.startsWith(sign.repeat(3))) continue;
    const code = line.slice(1).trim();
    if (/^(\/\/|\/\*|\*)/.test(code) || /^(import|export)\b.*\bfrom\b/.test(code)) continue;
    out.push(...(code.match(NUMBER) ?? []), ...(code.match(STRING) ?? []));
  }
  return out;
}

function difference(a: string[], b: string[]): string[] {
  const left = [...b];
  return a.filter((x) => {
    const i = left.indexOf(x);
    if (i < 0) return true;
    left.splice(i, 1);
    return false;
  });
}

/** What a change justified as having no behaviour change shows of one that has. */
function suspicions(source: Source, path: string, newTests: string[]): string[] {
  const reasons: string[] = [];
  if (newTests.length)
    reasons.push(
      `it adds test case(s): ${newTests
        .slice(0, 3)
        .map((t) => `"${t}"`)
        .join(", ")}`,
    );
  const diff = source.diff(path, 0);
  const removed = literalsOf(diff, "-");
  const added = literalsOf(diff, "+");
  const gone = difference(removed, added);
  const fresh = difference(added, removed);
  if (gone.length || fresh.length)
    reasons.push(
      `it changes numbers or strings: ${gone.slice(0, 3).join(", ") || "none"} became ${fresh.slice(0, 3).join(", ") || "none"}`,
    );
  return reasons;
}
