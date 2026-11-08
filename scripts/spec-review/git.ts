import { execFileSync } from "node:child_process";
import type { ChangedFile, Source } from "./types.ts";

function git(repo: string, args: string[], allowFailure = false): string {
  try {
    return execFileSync("git", args, {
      cwd: repo,
      encoding: "utf8",
      maxBuffer: 64 * 1024 * 1024,
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (e) {
    if (allowFailure) return "";
    const stderr = (e as { stderr?: Buffer | string }).stderr?.toString().trim();
    throw new Error(`git ${args.join(" ")} failed${stderr ? `: ${stderr}` : ""}`, { cause: e });
  }
}

export const refExists = (repo: string, ref: string): boolean => {
  try {
    execFileSync("git", ["rev-parse", "--verify", "--quiet", `${ref}^{commit}`], { cwd: repo, stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
};

const STATUS: Record<string, ChangedFile["status"]> = {
  A: "added",
  M: "modified",
  D: "deleted",
  R: "renamed",
  C: "added",
  T: "modified",
};

/** `git diff --name-status -z -M`: status, then one path (two for a rename). */
export function parseNameStatus(output: string): ChangedFile[] {
  const parts = output.split("\0");
  if (parts.at(-1) === "") parts.pop();
  const files: ChangedFile[] = [];
  for (let i = 0; i < parts.length;) {
    const code = parts[i++] ?? "";
    if (!code) continue;
    const status = STATUS[code[0]!];
    if (!status) throw new Error(`Unknown Git status "${code}"`);
    if (code[0] === "R" || code[0] === "C") {
      const oldPath = parts[i++]!;
      const path = parts[i++]!;
      files.push(code[0] === "R" ? { path, status, oldPath } : { path, status });
    } else files.push({ path: parts[i++]!, status });
  }
  return files.sort((a, b) => a.path.localeCompare(b.path));
}

/** The files changed between two refs as a pull request shows them (from the merge base), and what to read of them. */
export function gitSource(repo: string, base: string, head: string): Source {
  const range = `${base}...${head}`;
  const changed = parseNameStatus(git(repo, ["diff", "--name-status", "-z", "-M", range]));
  const messages = git(repo, ["log", "--format=%B%x00", `${base}..${head}`])
    .split("\0")
    .map((m) => m.trim())
    .filter(Boolean);
  const tree = git(repo, ["ls-tree", "-r", "--name-only", "-z", head]).split("\0").filter(Boolean);
  const mergeBase = git(repo, ["merge-base", base, head]).trim() || base;
  const show = (ref: string, path: string) => {
    try {
      return execFileSync("git", ["show", `${ref}:${path}`], {
        cwd: repo,
        encoding: "utf8",
        maxBuffer: 64 * 1024 * 1024,
        stdio: ["ignore", "pipe", "ignore"],
      });
    } catch {
      return undefined;
    }
  };
  return {
    base,
    head,
    changed,
    messages,
    tree,
    readHead: (path) => show(head, path),
    readBase: (path) => show(mergeBase, path),
    diff: (path, context, ignoreSpace) =>
      git(
        repo,
        ["diff", `-U${context}`, ...(ignoreSpace ? ["-w", "--ignore-blank-lines"] : []), range, "--", path],
        true,
      ),
  };
}
