import { parseRequirements, adrFile, specPath } from "./specs.ts";
import type { ModelFinding, Rejected, Source } from "./types.ts";

const squash = (s: string) => s.replace(/\s+/g, " ").trim();
const MIN_QUOTE = 12;
/** A quote may span a few lines of a paragraph. */
const WINDOW = 8;

/** The 1-based line where a quote starts in a text, or 0 when the text does not hold it. */
export function locateQuote(text: string, quote: string): number {
  const wanted = squash(quote);
  if (wanted.length < MIN_QUOTE) return 0;
  const lines = text.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const own = squash(lines[i]!);
    if (!own) continue;
    // The quote starts on this line when it is found in the window and begins before the line ends.
    const at = squash(lines.slice(i, i + WINDOW).join("\n")).indexOf(wanted);
    if (at >= 0 && at <= own.length) return i + 1;
  }
  return 0;
}

/** What the model was shown: the only files and records a finding may rely on. */
export interface Shown {
  capability: string;
  /** Records (`NNNN`) put in the prompt. */
  records: string[];
  /** Code and test files put in the prompt. */
  files: string[];
}

/**
 * Keeps the findings whose evidence the program checks itself: both files were shown to the model and exist, each
 * quote is in its file, the requirement or record exists. The lines come from where the quotes are found.
 */
export function verifyFindings(
  source: Source,
  shown: Shown,
  findings: ModelFinding[],
): { kept: ModelFinding[]; rejected: Rejected[] } {
  const kept: ModelFinding[] = [];
  const rejected: Rejected[] = [];
  const requirements = parseRequirements(source.readHead(specPath(shown.capability)) ?? "");
  const seen = new Set<string>();

  for (const found of findings) {
    let f = found;
    const reject = (reason: string) => rejected.push({ requirement: f.requirement, reason });

    const adr = /^(?:ADR\s*)?(\d{4})$/i.exec(f.requirement.trim())?.[1];
    if (adr) {
      if (!shown.records.includes(adr)) {
        reject(`ADR ${adr} was not part of the context`);
        continue;
      }
      f = { ...f, requirement: `ADR ${adr}` };
    } else {
      const wanted = squash(f.requirement.replace(/^Requirement:\s*/i, "")).toLowerCase();
      const named = requirements.find((r) => squash(r.name).toLowerCase() === wanted);
      if (!named) {
        reject(`no requirement named "${f.requirement}" in ${specPath(shown.capability)}`);
        continue;
      }
      // The name as the spec writes it, whatever the model made of it.
      f = { ...f, requirement: named.name };
    }

    const allowedSpecs = [
      specPath(shown.capability),
      ...shown.records.map((n) => adrFile(source.tree, n)).filter((p): p is string => !!p),
    ];
    if (!allowedSpecs.includes(f.spec.file)) {
      reject(`spec file ${f.spec.file} was not part of the context`);
      continue;
    }
    const specText = source.readHead(f.spec.file);
    const specLine = specText === undefined ? 0 : locateQuote(specText, f.spec.quote);
    if (!specLine) {
      reject(`the spec quote is not in ${f.spec.file}`);
      continue;
    }

    if (!shown.files.includes(f.code.file)) {
      reject(`code file ${f.code.file} was not part of the context`);
      continue;
    }
    // A deleted file is read from the base.
    const codeText = source.readHead(f.code.file) ?? source.readBase(f.code.file);
    if (codeText === undefined) {
      reject(`code file ${f.code.file} does not exist`);
      continue;
    }
    const codeLine = locateQuote(codeText, f.code.quote);
    if (!codeLine) {
      reject(`the code quote is not in ${f.code.file}`);
      continue;
    }

    const key = `${f.requirement}|${f.spec.file}:${specLine}|${f.code.file}:${codeLine}`;
    if (seen.has(key)) continue;
    seen.add(key);
    kept.push({ ...f, spec: { ...f.spec, line: specLine }, code: { ...f.code, line: codeLine } });
  }
  return { kept, rejected };
}

/** A verified finding that stops a push: high severity, and a confidence that is not low. */
export const blocks = (f: ModelFinding): boolean => f.severity === "high" && f.confidence !== "low";
