import { spawnSync } from "node:child_process";

export type SpecValidation =
  { state: "passed" } | { state: "failed"; output: string } | { state: "skipped"; reason: string };

/** `openspec validate --all --no-interactive`, when the tool is installed. A missing tool is a skipped check, never a pass. */
export function validateSpecs(cwd: string): SpecValidation {
  const run = spawnSync("openspec", ["validate", "--all", "--no-interactive"], { cwd, encoding: "utf8" });
  if (run.error) {
    const missing = (run.error as NodeJS.ErrnoException).code === "ENOENT";
    return {
      state: "skipped",
      reason: missing
        ? "openspec is not installed (nix develop provides it)"
        : `openspec could not run: ${run.error.message}`,
    };
  }
  if (run.status === 0) return { state: "passed" };
  const output = `${run.stdout}${run.stderr}`
    .split("\n")
    .filter((l) => /✗|FAIL|error|ERROR|failed/i.test(l))
    .slice(0, 12)
    .join("\n");
  return { state: "failed", output: output || `openspec exited with ${run.status}` };
}
