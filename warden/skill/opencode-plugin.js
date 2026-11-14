// Warden for OpenCode. Written by `warden init --agent opencode`; do not edit it: Warden refuses writes to it.
//
// OpenCode has no external-command hooks, so this plugin calls `warden hook opencode <event>` for every tool call and prompt
// and acts on the JSON that comes back: it throws to refuse (OpenCode shows the message to the model), replaces the tool's
// arguments in place, and replaces the tool's output after it ran. If Warden cannot be run or answers nonsense, the call is
// refused: a guard that fails open guards nothing.
import { spawnSync } from "node:child_process";

const WARDEN = process.env.WARDEN_BIN || "warden";

function ask(event, payload) {
  const run = spawnSync(WARDEN, ["hook", "opencode", event], {
    input: JSON.stringify(payload),
    encoding: "utf8",
    timeout: 20000,
  });
  if (run.error || run.status !== 0) {
    const why = run.error ? run.error.message : "exit " + run.status;
    throw new Error("Warden could not judge this call (" + why + "), so it is refused.");
  }
  try {
    return JSON.parse(run.stdout || "{}");
  } catch {
    throw new Error("Warden answered something unreadable, so the call is refused.");
  }
}

export const WardenPlugin = async ({ directory }) => ({
  "tool.execute.before": async (input, output) => {
    const answer = ask("tool.before", { tool: input.tool, args: output.args, sessionID: input.sessionID, cwd: directory });
    if (answer.decision === "deny" || answer.decision === "ask") {
      throw new Error(answer.reason || "Refused by Warden.");
    }
    if (answer.args && typeof answer.args === "object") Object.assign(output.args, answer.args);
  },
  "tool.execute.after": async (input, output) => {
    const answer = ask("tool.after", {
      tool: input.tool,
      args: input.args,
      output: typeof output.output === "string" ? output.output : "",
      sessionID: input.sessionID,
      cwd: directory,
    });
    if (typeof answer.output === "string") output.output = answer.output;
  },
  "chat.message": async (input, output) => {
    const text = (output.parts || []).filter((part) => part.type === "text").map((part) => part.text).join("\n");
    if (!text) return;
    const answer = ask("prompt", { prompt: text, sessionID: input.sessionID, cwd: directory });
    if (answer.block) throw new Error(answer.reason || "Refused by Warden.");
  },
});
