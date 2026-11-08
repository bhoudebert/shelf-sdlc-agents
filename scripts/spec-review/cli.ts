import { execFileSync } from "node:child_process";
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { parseArgs } from "node:util";
import { gitSource, refExists } from "./git.ts";
import { ghIn, publish, PublishError } from "./publish.ts";
import { ollama, openai, type Provider } from "./provider.ts";
import { describeState, githubAnnotations, renderMarkdown } from "./report.ts";
import { runAuditReport, runReview } from "./run.ts";
import type { NoSpec, Report } from "./types.ts";

export const USAGE = `Usage: npm run spec:review -- [options]

  --base <ref>          what the change is compared with (default origin/main, or SPEC_REVIEW_BASE)
  --head <ref>          the change (default HEAD)
  --provider <name>     "ollama" (OLLAMA_HOST) or "openai" (SPEC_REVIEW_BASE_URL: LiteLLM, vLLM...) asks a model; "none" runs the
                        deterministic checks only (default none; the hook: SPEC_REVIEW_PROVIDER, else ollama when a model is set)
  --model <name>        the model (or SPEC_REVIEW_MODEL); for "openai" the name the server serves
  --no-spec <reason>    the change has no behaviour change, so no spec change is needed
  --out <folder>        where report.json and report.md go (default .spec-review)
  --format <text|github>  github also prints workflow annotations and fills the job summary
  --ignore-commit-lines a "No-Spec:" line in a commit is not a justification (the pull-request check: only the label counts)
  --skip-openspec       do not run openspec validate (another job does)
  --require-review      a model review that did not complete also fails the command
  --max-capabilities <n>  capabilities asked about, one model call each (default 4)
  --audit               check the whole tree at --head with no base, to clean up what earlier changes left (no model)
  --publish             after a completed model review, show it on GitHub: a status on the commit and a comment on the pull request
  --pr <number>         the pull request for --publish (default: the one of the current branch)
  --hook                the pre-push hook: the model runs when SPEC_REVIEW_MODEL is set; a review that cannot run never blocks
  --repo <folder>       the repository (default the current folder)

Exit: 0 nothing blocks, 1 a blocking finding, 2 the review itself could not run.`;

export interface Io {
  out(text: string): void;
  err(text: string): void;
}

const stdio: Io = { out: (t) => console.log(t), err: (t) => console.error(t) };

/** A short text for a terminal or a hook. */
export function summaryText(report: Report): string {
  const lines = [
    report.base === "(audit)"
      ? `spec review, audit of ${report.head}`
      : `spec review ${report.base}...${report.head}: ${report.changed.length} file(s) changed`,
  ];
  if (report.base !== "(audit)" && report.changed.length === 0)
    lines.push(
      "  nothing to compare: no file differs between the two refs. The review reads commits: commit your work on a branch, or give an older --base (or --audit for the whole repository).",
    );
  for (const f of report.findings.filter((x) => x.level !== "info")) {
    lines.push(
      `  ${f.level === "error" ? "error  " : "warning"} ${f.rule}${f.file ? ` ${f.file}${f.line ? `:${f.line}` : ""}` : ""}: ${f.message.split("\n")[0]}`,
    );
  }
  if (report.noSpec) lines.push(`  no spec change needed (${report.noSpec.source}): ${report.noSpec.reason}`);
  for (const s of report.skippedChecks) lines.push(`  skipped: ${s}`);
  lines.push(`  model review: ${describeState(report.review.status)}`);
  if (report.review.findings.length) {
    for (const f of report.review.findings)
      lines.push(
        `  model ${f.severity}/${f.confidence}: ${f.requirement} — ${f.spec.file}:${f.spec.line} vs ${f.code.file}:${f.code.line}: ${f.explanation} (proposed: ${f.action})`,
      );
  }
  if (report.review.rejected.length)
    lines.push(`  ${report.review.rejected.length} model finding(s) dropped: evidence not found`);
  lines.push(report.blockers.length ? `BLOCKING (${report.blockers.length}):` : "nothing blocks");
  for (const b of report.blockers) lines.push(`  - ${b}`);
  return lines.join("\n");
}

export async function main(argv: string[], env: NodeJS.ProcessEnv = process.env, io: Io = stdio): Promise<number> {
  let values;
  try {
    ({ values } = parseArgs({
      args: argv,
      options: {
        base: { type: "string" },
        head: { type: "string" },
        provider: { type: "string" },
        model: { type: "string" },
        "no-spec": { type: "string" },
        out: { type: "string" },
        format: { type: "string" },
        "skip-openspec": { type: "boolean" },
        "ignore-commit-lines": { type: "boolean" },
        "require-review": { type: "boolean" },
        "max-capabilities": { type: "string" },
        hook: { type: "boolean" },
        audit: { type: "boolean" },
        publish: { type: "boolean" },
        pr: { type: "string" },
        repo: { type: "string" },
        help: { type: "boolean", short: "h" },
      },
    }));
  } catch (e) {
    io.err(`${(e as Error).message}\n\n${USAGE}`);
    return 2;
  }
  if (values.help) {
    io.out(USAGE);
    return 0;
  }

  const hook = Boolean(values.hook);
  if (hook && env.SKIP_SPEC_REVIEW) {
    io.err("spec review skipped (SKIP_SPEC_REVIEW is set)");
    return 0;
  }
  // A hook never blocks on its own failure: the pull-request check enforces the rule.
  const technical = hook ? 0 : 2;
  const repo = resolve(values.repo ?? ".");
  const head = values.head ?? "HEAD";
  const base =
    values.base ?? env.SPEC_REVIEW_BASE ?? ["origin/main", "main"].find((r) => refExists(repo, r)) ?? "origin/main";

  const providerName =
    values.provider ?? (hook ? (env.SPEC_REVIEW_MODEL ? (env.SPEC_REVIEW_PROVIDER ?? "ollama") : "none") : "none");
  let provider: Provider | null = null;
  if (providerName === "ollama" || providerName === "openai") {
    const model = values.model ?? env.SPEC_REVIEW_MODEL;
    if (!model) {
      io.err(`The ${providerName} provider needs a model: --model <name> or SPEC_REVIEW_MODEL.`);
      return 2;
    }
    const timeoutMs = env.SPEC_REVIEW_TIMEOUT_MS ? Number(env.SPEC_REVIEW_TIMEOUT_MS) : undefined;
    if (providerName === "ollama") {
      provider = ollama({
        model,
        host: env.OLLAMA_HOST,
        think: env.SPEC_REVIEW_THINK === "1",
        numCtx: env.SPEC_REVIEW_NUM_CTX ? Number(env.SPEC_REVIEW_NUM_CTX) : undefined,
        timeoutMs,
      });
    } else {
      if (!env.SPEC_REVIEW_BASE_URL) {
        io.err(
          "The openai provider needs the API root of the server: SPEC_REVIEW_BASE_URL (e.g. http://localhost:4000/v1).",
        );
        return 2;
      }
      let extraBody: Record<string, unknown> | undefined;
      if (env.SPEC_REVIEW_EXTRA_BODY) {
        try {
          extraBody = JSON.parse(env.SPEC_REVIEW_EXTRA_BODY) as Record<string, unknown>;
          if (!extraBody || typeof extraBody !== "object" || Array.isArray(extraBody)) throw new Error("not an object");
        } catch {
          io.err("SPEC_REVIEW_EXTRA_BODY must be a JSON object.");
          return 2;
        }
      }
      provider = openai({
        model,
        baseUrl: env.SPEC_REVIEW_BASE_URL,
        apiKey: env.SPEC_REVIEW_API_KEY,
        extraBody,
        maxTokens: env.SPEC_REVIEW_MAX_TOKENS ? Number(env.SPEC_REVIEW_MAX_TOKENS) : undefined,
        timeoutMs,
      });
    }
  } else if (providerName !== "none") {
    io.err(`Unknown provider "${providerName}": ollama, openai or none.`);
    return 2;
  }

  if (values.publish && hook) io.err("--publish is ignored by the hook: a push never posts to GitHub.");
  if (values.publish && !hook && (!provider || values.audit)) {
    io.err("--publish shows a model review: it needs --provider ollama or openai, and not --audit.");
    return 2;
  }

  const noSpec: NoSpec | undefined = values["no-spec"]
    ? { reason: values["no-spec"], source: "option" }
    : env.SPEC_REVIEW_NO_SPEC
      ? { reason: env.SPEC_REVIEW_NO_SPEC, source: "label" }
      : undefined;

  let report: Report;
  try {
    if (values.audit && provider) {
      io.err("--audit does not call a model yet: leave out --provider.");
      return 2;
    }
    if (values.audit) {
      if (!refExists(repo, head)) throw new Error(`the head "${head}" is not a Git ref here`);
      const source = gitSource(repo, head, head);
      report = runAuditReport(source, { openspec: values["skip-openspec"] ? false : undefined, cwd: repo });
    } else {
      if (!refExists(repo, base)) throw new Error(`the base "${base}" is not a Git ref here (git fetch, or --base)`);
      if (!refExists(repo, head)) throw new Error(`the head "${head}" is not a Git ref here`);
      const source = gitSource(repo, base, head);
      if (hook && source.changed.length === 0) return 0;
      report = await runReview(source, {
        noSpec,
        commitLines: !values["ignore-commit-lines"],
        provider,
        openspec: values["skip-openspec"] ? false : undefined,
        requireReview: values["require-review"],
        maxCapabilities: values["max-capabilities"] ? Number(values["max-capabilities"]) : undefined,
        cwd: repo,
        onProgress: (m) => io.err(m),
      });
    }
  } catch (e) {
    io.err(`spec review could not run: ${(e as Error).message}`);
    return technical;
  }

  const out = resolve(repo, values.out ?? ".spec-review");
  try {
    mkdirSync(out, { recursive: true });
    writeFileSync(resolve(out, "report.json"), `${JSON.stringify(report, null, 2)}\n`);
    writeFileSync(resolve(out, "report.md"), renderMarkdown(report));
  } catch (e) {
    io.err(`the reports could not be written to ${out}: ${(e as Error).message}`);
  }

  io.out(summaryText(report));
  if (values.format === "github") {
    for (const line of githubAnnotations(report)) io.out(line);
    if (env.GITHUB_STEP_SUMMARY) appendFileSync(env.GITHUB_STEP_SUMMARY, `${renderMarkdown(report)}\n`);
  }
  let publishFailed = false;
  if (values.publish && !hook) {
    try {
      const sha = execFileSync("git", ["rev-parse", head], { cwd: repo, encoding: "utf8" }).trim();
      const result = publish(report, { sha, pr: values.pr ? Number(values.pr) : undefined, gh: ghIn(repo) });
      io.out(
        result.published
          ? `published on ${result.sha.slice(0, 7)}: status ${result.state} (${result.description}); ${
              result.pr === null ? "no pull request found for a comment" : `comment ${result.comment} on #${result.pr}`
            }`
          : `not published: ${result.reason}`,
      );
    } catch (e) {
      publishFailed = true;
      io.err(`could not publish: ${e instanceof PublishError ? e.message : (e as Error).message}`);
    }
  }
  if (report.blockers.length) {
    if (hook)
      io.err(
        "push blocked by the spec review. The checks are in the pull request too; `git push --no-verify` skips this hook, not those.",
      );
    return 1;
  }
  return publishFailed ? 2 : 0;
}
