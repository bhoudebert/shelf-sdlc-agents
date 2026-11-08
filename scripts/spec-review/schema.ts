import { ACTIONS, CONFIDENCES, KINDS, SEVERITIES, type Evidence, type ModelFinding } from "./types.ts";

const evidence = {
  type: "object",
  properties: {
    file: { type: "string", description: "Path of the file, exactly as given in the data" },
    line: { type: "integer", description: "Line number, if known" },
    quote: {
      type: "string",
      description: "An exact quote from the file: a sentence or a line, copied character for character",
    },
  },
  required: ["file", "line", "quote"],
} as const;

/** The answer asked of the model; sent as the `format` of the request and checked again by `parseFindings`. */
export const FINDINGS_SCHEMA = {
  type: "object",
  properties: {
    findings: {
      type: "array",
      items: {
        type: "object",
        properties: {
          kind: { type: "string", enum: [...KINDS] },
          severity: { type: "string", enum: [...SEVERITIES] },
          confidence: { type: "string", enum: [...CONFIDENCES] },
          requirement: { type: "string", description: "The name of the requirement, or ADR followed by the number" },
          spec: evidence,
          code: evidence,
          explanation: { type: "string" },
          action: { type: "string", enum: [...ACTIONS] },
        },
        required: ["kind", "severity", "confidence", "requirement", "spec", "code", "explanation", "action"],
      },
    },
  },
  required: ["findings"],
} as const;

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

function parseEvidence(value: unknown, where: string): Evidence {
  if (!isObject(value)) throw new Error(`${where} is not an object`);
  const { file, line, quote } = value;
  if (typeof file !== "string" || !file) throw new Error(`${where}.file is not a string`);
  if (typeof quote !== "string" || !quote) throw new Error(`${where}.quote is not a string`);
  return { file, line: typeof line === "number" && Number.isFinite(line) ? Math.trunc(line) : 0, quote };
}

const oneOf = <T extends string>(value: unknown, allowed: readonly T[], where: string): T => {
  if (typeof value !== "string" || !(allowed as readonly string[]).includes(value))
    throw new Error(`${where} must be one of ${allowed.join(", ")}`);
  return value as T;
};

/** The model's text as findings, or an error saying what does not follow the schema. */
export function parseFindings(text: string): { ok: true; findings: ModelFinding[] } | { ok: false; reason: string } {
  let json: unknown;
  try {
    json = JSON.parse(text);
  } catch {
    return { ok: false, reason: "the answer is not valid JSON" };
  }
  try {
    if (!isObject(json) || !Array.isArray(json.findings)) throw new Error("`findings` is not an array");
    const findings = json.findings.map((raw, i): ModelFinding => {
      const at = `findings[${i}]`;
      if (!isObject(raw)) throw new Error(`${at} is not an object`);
      if (typeof raw.requirement !== "string" || !raw.requirement) throw new Error(`${at}.requirement is not a string`);
      if (typeof raw.explanation !== "string" || !raw.explanation) throw new Error(`${at}.explanation is not a string`);
      return {
        kind: oneOf(raw.kind, KINDS, `${at}.kind`),
        severity: oneOf(raw.severity, SEVERITIES, `${at}.severity`),
        confidence: oneOf(raw.confidence, CONFIDENCES, `${at}.confidence`),
        requirement: raw.requirement,
        spec: parseEvidence(raw.spec, `${at}.spec`),
        code: parseEvidence(raw.code, `${at}.code`),
        explanation: raw.explanation,
        action: oneOf(raw.action, ACTIONS, `${at}.action`),
      };
    });
    return { ok: true, findings };
  } catch (e) {
    return { ok: false, reason: `the answer does not follow the schema: ${(e as Error).message}` };
  }
}
