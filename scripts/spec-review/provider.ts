/** A model that answers a prompt with JSON that follows a schema: Ollama's own API, or any OpenAI-compatible server. */
export interface Provider {
  name: string;
  model: string;
  complete(request: { system: string; user: string; schema: object }): Promise<string>;
}

/** The server does not answer, or does not have the model: the review cannot run. */
export class Unavailable extends Error {}

/** The server answered, but not with something usable. */
export class BadAnswer extends Error {}

export interface OllamaOptions {
  host?: string;
  model: string;
  /**
   * Let a thinking model think (default off). Reasoning spends the context window before the constrained answer
   * starts: a thinking model then returns nothing, slowly.
   */
  think?: boolean;
  /** Context window asked of the server; Ollama's default (2 to 4 thousand tokens) would cut the prompt. */
  numCtx?: number;
  timeoutMs?: number;
  fetch?: typeof fetch;
}

export function ollama(options: OllamaOptions): Provider {
  const host = (options.host ?? "http://127.0.0.1:11434").replace(/\/+$/, "");
  const call = options.fetch ?? fetch;
  return {
    name: "ollama",
    model: options.model,
    async complete({ system, user, schema }) {
      let response: Response;
      try {
        response = await call(`${host}/api/chat`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            model: options.model,
            stream: false,
            think: options.think ?? false,
            format: schema,
            options: { temperature: 0, num_ctx: options.numCtx ?? 16384 },
            messages: [
              { role: "system", content: system },
              { role: "user", content: user },
            ],
          }),
          signal: AbortSignal.timeout(options.timeoutMs ?? 300_000),
        });
      } catch (e) {
        const cause = (e as { cause?: { code?: string } }).cause?.code;
        const timeout = (e as Error).name === "TimeoutError";
        throw new Unavailable(
          timeout
            ? `Ollama at ${host} did not answer in time`
            : `Ollama at ${host} is not reachable${cause ? ` (${cause})` : ""}`,
        );
      }
      if (response.status === 404)
        throw new Unavailable(`Ollama at ${host} has no model "${options.model}": ollama pull ${options.model}`);
      if (!response.ok) throw new Unavailable(`Ollama at ${host} answered ${response.status}`);
      let body: { message?: { content?: unknown } };
      try {
        body = (await response.json()) as typeof body;
      } catch {
        throw new BadAnswer("Ollama's answer is not JSON");
      }
      const content = body.message?.content;
      if (typeof content !== "string") throw new BadAnswer("Ollama's answer has no message");
      return content;
    },
  };
}

export interface OpenAiOptions {
  /** The API root, `/v1` included (LiteLLM: `http://localhost:4000/v1`); `/chat/completions` is added. */
  baseUrl: string;
  model: string;
  /** Sent as a bearer token when the server asks for one (a LiteLLM key). Never printed. */
  apiKey?: string;
  /** Fields merged into the request body, for what a gateway needs and this adapter does not know (a thinking switch). */
  extraBody?: Record<string, unknown>;
  /**
   * Longest answer asked of the server (default 4096). A list of findings is short: without a cap a model that loops
   * generates until the context window is full, minutes later, and the server may go on after the client gave up.
   */
  maxTokens?: number;
  timeoutMs?: number;
  fetch?: typeof fetch;
}

/** Any server that speaks `POST /chat/completions` with a JSON-schema response format: LiteLLM, vLLM, Ollama's /v1... */
export function openai(options: OpenAiOptions): Provider {
  const base = options.baseUrl.replace(/\/+$/, "");
  const call = options.fetch ?? fetch;
  return {
    name: "openai",
    model: options.model,
    async complete({ system, user, schema }) {
      let response: Response;
      try {
        response = await call(`${base}/chat/completions`, {
          method: "POST",
          headers: {
            "content-type": "application/json",
            ...(options.apiKey ? { authorization: `Bearer ${options.apiKey}` } : {}),
          },
          body: JSON.stringify({
            temperature: 0,
            max_tokens: options.maxTokens ?? 4096,
            ...options.extraBody,
            model: options.model,
            stream: false,
            response_format: { type: "json_schema", json_schema: { name: "findings", strict: true, schema } },
            messages: [
              { role: "system", content: system },
              { role: "user", content: user },
            ],
          }),
          signal: AbortSignal.timeout(options.timeoutMs ?? 300_000),
        });
      } catch (e) {
        const cause = (e as { cause?: { code?: string } }).cause?.code;
        const timeout = (e as Error).name === "TimeoutError";
        throw new Unavailable(
          timeout
            ? `The server at ${base} did not answer in time`
            : `The server at ${base} is not reachable${cause ? ` (${cause})` : ""}`,
        );
      }
      if (response.status === 401 || response.status === 403)
        throw new Unavailable(`The server at ${base} refused the key (${response.status}): check SPEC_REVIEW_API_KEY`);
      if (response.status === 404 || response.status === 400)
        throw new Unavailable(
          `The server at ${base} answered ${response.status}: is "${options.model}" a model it serves, and is the base URL the API root (…/v1)?`,
        );
      if (!response.ok) throw new Unavailable(`The server at ${base} answered ${response.status}`);
      let body: { choices?: { message?: { content?: unknown }; finish_reason?: unknown }[] };
      try {
        body = (await response.json()) as typeof body;
      } catch {
        throw new BadAnswer("The answer is not JSON");
      }
      const choice = body.choices?.[0];
      if (choice?.finish_reason === "length")
        throw new BadAnswer(
          `The answer was cut off at ${options.maxTokens ?? 4096} tokens (a model that does not stop; thinking on?): SPEC_REVIEW_MAX_TOKENS, SPEC_REVIEW_EXTRA_BODY`,
        );
      const content = choice?.message?.content;
      if (typeof content !== "string") throw new BadAnswer("The answer has no message");
      return content;
    },
  };
}
