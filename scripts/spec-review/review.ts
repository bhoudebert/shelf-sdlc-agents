import { buildContext, DEFAULT_BUDGET, SYSTEM_PROMPT, userPrompt } from "./context.ts";
import { BadAnswer, Unavailable, type Provider } from "./provider.ts";
import { parseFindings, FINDINGS_SCHEMA } from "./schema.ts";
import { capabilitiesOfTree, type CodeMap } from "./specs.ts";
import type { ModelFinding, NoSpec, Rejected, ReviewReport, Source, Touched } from "./types.ts";
import { verifyFindings } from "./verify.ts";

export const notRequested = (): ReviewReport => ({
  status: { state: "not-requested" },
  reviewed: [],
  skipped: [],
  findings: [],
  rejected: [],
});

export interface ReviewOptions {
  budget?: number;
  /** How many capabilities are asked about: each is a model call. */
  maxCapabilities?: number;
  onProgress?: (message: string) => void;
  /** The change is justified as having no behaviour change: the model is asked whether that is true. */
  claim?: NoSpec | null;
}

/** Asks the provider about each touched capability, one call each, and keeps only the findings that check out. */
export async function reviewWithModel(
  source: Source,
  touched: Touched[],
  map: CodeMap,
  provider: Provider,
  options: ReviewOptions = {},
): Promise<ReviewReport> {
  const known = new Set(capabilitiesOfTree(source.tree));
  const wanted = touched.map((t) => t.capability).filter((c) => known.has(c));
  const maxCapabilities = options.maxCapabilities ?? 4;
  const queue = wanted.slice(0, maxCapabilities);
  const report: ReviewReport = {
    status: queue.length
      ? { state: "completed", provider: provider.name, model: provider.model }
      : { state: "nothing-to-review" },
    reviewed: [],
    skipped: wanted.slice(maxCapabilities),
    findings: [],
    rejected: [],
  };
  const findings: ModelFinding[] = [];
  const rejected: Rejected[] = [];

  for (const capability of queue) {
    options.onProgress?.(`reviewing ${capability} with ${provider.name}/${provider.model}`);
    const { text, shown } = buildContext(source, capability, map, options.budget ?? DEFAULT_BUDGET);
    try {
      const answer = await provider.complete({
        system: SYSTEM_PROMPT,
        user: userPrompt(capability, source.base, source.head, text, options.claim),
        schema: FINDINGS_SCHEMA,
      });
      const parsed = parseFindings(answer);
      if (!parsed.ok) {
        report.status = { state: "failed", reason: `${capability}: ${parsed.reason}` };
        report.skipped.push(...queue.slice(queue.indexOf(capability)));
        break;
      }
      const checked = verifyFindings(source, shown, parsed.findings);
      findings.push(...checked.kept);
      rejected.push(...checked.rejected);
      report.reviewed.push(capability);
    } catch (e) {
      if (!(e instanceof Unavailable || e instanceof BadAnswer)) throw e;
      report.status =
        e instanceof Unavailable
          ? { state: "unavailable", reason: e.message }
          : { state: "failed", reason: `${capability}: ${e.message}` };
      report.skipped.push(...queue.slice(queue.indexOf(capability)));
      break;
    }
  }
  report.findings = findings;
  report.rejected = rejected;
  return report;
}
