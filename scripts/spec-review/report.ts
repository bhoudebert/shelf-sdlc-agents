import type { Finding, ModelFinding, Report, ReviewState } from "./types.ts";

export function describeState(state: ReviewState): string {
  switch (state.state) {
    case "not-requested":
      return "Not requested: only the deterministic checks ran.";
    case "nothing-to-review":
      return "Requested, but no capability is touched by this change: the model was not contacted.";
    case "unavailable":
      return `NOT RUN, unavailable: ${state.reason}. This is not a review that found nothing.`;
    case "failed":
      return `NOT COMPLETED, the answer was unusable: ${state.reason}. This is not a review that found nothing.`;
    case "completed":
      return `Completed with ${state.provider}/${state.model}. A model can miss a drift or flag a change that is fine: it is a lead for the author, not a verdict.`;
  }
}

const mark = { error: "❌", warning: "⚠️", info: "ℹ️" } as const;
const where = (f: { file?: string; line?: number }) => (f.file ? ` \`${f.file}${f.line ? `:${f.line}` : ""}\`` : "");

function modelFinding(f: ModelFinding): string {
  return [
    `- **${f.severity}** (confidence ${f.confidence}, ${f.kind}) — ${f.requirement}`,
    `  - spec: \`${f.spec.file}:${f.spec.line}\` — “${f.spec.quote}”`,
    `  - code: \`${f.code.file}:${f.code.line}\` — “${f.code.quote}”`,
    `  - ${f.explanation}`,
    `  - proposed action: ${f.action}`,
  ].join("\n");
}

export function renderMarkdown(report: Report): string {
  const out: string[] = [];
  out.push(`# Spec review: \`${report.base}\`...\`${report.head}\``, "");
  out.push(report.blockers.length ? `**Blocking: ${report.blockers.length}**` : "**Nothing blocks.**", "");
  for (const b of report.blockers) out.push(`- ${b}`);
  if (report.blockers.length) out.push("");

  out.push("## Deterministic checks", "");
  const counts = (level: Finding["level"]) => report.findings.filter((f) => f.level === level).length;
  out.push(
    `${report.changed.length} file(s) changed; ${counts("error")} error(s), ${counts("warning")} warning(s), ${counts("info")} note(s).`,
    "",
  );
  for (const f of report.findings)
    out.push(`- ${mark[f.level]} \`${f.rule}\`${where(f)} — ${f.message.split("\n").join(" ")}`);
  if (report.noSpec)
    out.push("", `No spec change needed, as stated (${report.noSpec.source}): ${report.noSpec.reason}`);
  for (const s of report.skippedChecks) out.push(`- ⏭️ skipped: ${s}`);
  out.push("");

  out.push("## Capabilities touched", "");
  if (!report.touched.length) out.push("None.");
  for (const t of report.touched) out.push(`- **${t.capability}**: ${t.reasons.join("; ")}`);
  if (report.unmapped.length) out.push("", `Not in the code map: ${report.unmapped.map((p) => `\`${p}\``).join(", ")}`);
  out.push("");

  out.push("## Model review", "", describeState(report.review.status), "");
  if (report.review.reviewed.length) out.push(`Asked about: ${report.review.reviewed.join(", ")}.`);
  if (report.review.skipped.length) out.push(`Not asked about: ${report.review.skipped.join(", ")}.`);
  if (report.review.findings.length)
    out.push("", "### Findings (evidence checked by the program)", "", ...report.review.findings.map(modelFinding));
  else if (report.review.status.state === "completed") out.push("", "No finding passed the evidence check.");
  if (report.review.rejected.length) {
    out.push("", `### Rejected (${report.review.rejected.length}): the evidence did not check out`, "");
    for (const r of report.review.rejected) out.push(`- ${r.requirement}: ${r.reason}`);
  }
  out.push("");
  return out.join("\n");
}

const escape = (s: string) => s.replace(/%/g, "%25").replace(/\r/g, "%0D").replace(/\n/g, "%0A");

/** GitHub Actions workflow commands: the findings appear on the files of the pull request. */
export function githubAnnotations(report: Report): string[] {
  const lines: string[] = [];
  for (const f of report.findings) {
    const level = f.level === "error" ? "error" : f.level === "warning" ? "warning" : "notice";
    const file = f.file && !f.file.endsWith("/") ? `file=${f.file},` : "";
    lines.push(`::${level} ${file}${f.line ? `line=${f.line},` : ""}title=spec-review ${f.rule}::${escape(f.message)}`);
  }
  for (const f of report.review.findings)
    lines.push(
      `::warning file=${f.spec.file},line=${f.spec.line},title=spec-review model::${escape(`${f.requirement}: ${f.explanation}`)}`,
    );
  return lines;
}
