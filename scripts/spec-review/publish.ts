import { execFileSync } from "node:child_process";
import { renderMarkdown } from "./report.ts";
import type { Report } from "./types.ts";
import { blocks } from "./verify.ts";

/** Runs `gh` with the arguments, and `input` on its standard input; returns what it prints. */
export type Gh = (args: string[], input?: string) => string;

export const ghIn =
  (cwd: string): Gh =>
  (args, input) =>
    execFileSync("gh", args, {
      cwd,
      encoding: "utf8",
      input,
      stdio: ["pipe", "pipe", "pipe"],
      maxBuffer: 16 * 1024 * 1024,
    });

export const STATUS_CONTEXT = "spec-review/local-model";
/** Finds the comment of the review on a pull request, so a later run updates it. */
export const COMMENT_MARKER = "<!-- spec-review:local-model -->";

export class PublishError extends Error {}

export type Published =
  | {
      published: true;
      sha: string;
      state: "success" | "failure";
      description: string;
      pr: number | null;
      comment: "created" | "updated" | "none";
    }
  | { published: false; reason: string };

const clip = (s: string, max: number) => (s.length <= max ? s : `${s.slice(0, max - 1)}…`);

/** A mention in the model's words must not notify anyone. */
export const defuse = (text: string): string => text.replace(/(^|[^\w`@])@(?=[\w-])/gm, "$1@​");

/** What the status says: the model, and what its review found. */
export function describe(report: Report): { state: "success" | "failure"; description: string } {
  const status = report.review.status;
  const model = status.state === "completed" ? `${status.provider}/${status.model}` : "model";
  const blocking = report.review.findings.filter(blocks).length;
  const advice = report.review.findings.length - blocking;
  const parts = [blocking ? `${blocking} blocking finding(s)` : "no blocking finding"];
  if (advice) parts.push(`${advice} advice`);
  if (report.review.rejected.length) parts.push(`${report.review.rejected.length} dropped: no evidence`);
  return { state: blocking ? "failure" : "success", description: clip(`${model}: ${parts.join(", ")}`, 140) };
}

/**
 * Shows a completed model review on GitHub: a status on the commit, and one comment on the pull request that a later run
 * updates. Nothing is posted for a review that did not complete, so a commit with no status is a commit the model has not
 * reviewed. Anyone with write access can post the same: it shows that a review ran, it does not prove it.
 */
export function publish(report: Report, options: { sha: string; pr?: number; gh: Gh; now?: Date }): Published {
  const { gh, sha } = options;
  if (report.review.status.state !== "completed" || report.review.reviewed.length === 0)
    return {
      published: false,
      reason: `the model review did not complete (${report.review.status.state}): nothing is posted`,
    };

  try {
    gh(["api", `repos/{owner}/{repo}/commits/${sha}`, "--jq", ".sha"]);
  } catch {
    throw new PublishError(`the commit ${sha.slice(0, 7)} is not on GitHub: push it first`);
  }

  let pr: number | null = options.pr ?? null;
  if (pr === null) {
    try {
      pr = Number(gh(["pr", "view", "--json", "number", "--jq", ".number"]).trim()) || null;
    } catch {
      pr = null;
    }
  }

  const { state, description } = describe(report);
  const status = [
    "api",
    "--method",
    "POST",
    `repos/{owner}/{repo}/statuses/${sha}`,
    "-f",
    `state=${state}`,
    "-f",
    `context=${STATUS_CONTEXT}`,
    "-f",
    `description=${description}`,
  ];
  try {
    gh(status);
  } catch (e) {
    throw new PublishError(`the status could not be posted: ${(e as Error).message.split("\n")[0]}`);
  }

  let comment: "created" | "updated" | "none" = "none";
  if (pr !== null) {
    const body = defuse(
      `${COMMENT_MARKER}\n**Spec review by a local model**, commit \`${sha.slice(0, 7)}\`, ${(options.now ?? new Date()).toISOString()}. ` +
        `Anyone with write access can post this: it shows that a review ran, it does not prove the review is right.\n\n${renderMarkdown(report)}`,
    );
    try {
      const existing = gh([
        "api",
        "--paginate",
        `repos/{owner}/{repo}/issues/${pr}/comments`,
        "--jq",
        `.[] | select(.body | contains("${COMMENT_MARKER}")) | .id`,
      ])
        .split("\n")
        .map((l) => l.trim())
        .find(Boolean);
      const payload = JSON.stringify({ body });
      if (existing) {
        gh(["api", "--method", "PATCH", `repos/{owner}/{repo}/issues/comments/${existing}`, "--input", "-"], payload);
        comment = "updated";
      } else {
        gh(["api", "--method", "POST", `repos/{owner}/{repo}/issues/${pr}/comments`, "--input", "-"], payload);
        comment = "created";
      }
    } catch (e) {
      throw new PublishError(
        `the status is posted, but the comment could not be: ${(e as Error).message.split("\n")[0]}`,
      );
    }
  }
  return { published: true, sha, state, description, pr, comment };
}
