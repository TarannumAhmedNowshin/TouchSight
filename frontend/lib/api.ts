import { Result, Sample } from "./types";

/** In production the browser talks to the engine directly (no proxy timeouts); locally Next.js proxies /api. */
const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
export const apiUrl = (path: string) => `${API_BASE}${path}`;

async function parse<T>(res: Response, fallback: string): Promise<T> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON error page from a proxy */
  }
  if (!res.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail;
    throw new Error(typeof detail === "string" ? detail : fallback);
  }
  return body as T;
}

export async function listSamples(): Promise<Sample[]> {
  const samples = await parse<Sample[]>(await fetch(apiUrl("/api/samples")), "Couldn't load samples.");
  return samples.map((s) => ({ ...s, url: apiUrl(s.url) }));
}

export async function convert(input: { file: File } | { sample: string }): Promise<Result> {
  const fd = new FormData();
  if ("file" in input) fd.append("file", input.file);
  else fd.append("sample", input.sample);
  const res = await fetch(apiUrl("/api/convert"), { method: "POST", body: fd });
  return parse<Result>(res, "Conversion failed. Try again or use a different image.");
}

export async function redesign(job: string, exclude: string[]): Promise<Result> {
  const res = await fetch(apiUrl("/api/redesign"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job, exclude }),
  });
  return parse<Result>(res, "Couldn't rebuild the page.");
}

export async function ask(job: string, question: string): Promise<{ answer: string; provider: string }> {
  const res = await fetch(apiUrl("/api/ask"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job, question }),
  });
  return parse(res, "Couldn't get an answer right now.");
}

/** Free hosting sleeps when idle. Ping until the engine answers; onSlow fires if it takes a while. */
export async function wake(onSlow: () => void, timeoutMs = 90_000): Promise<boolean> {
  const started = Date.now();
  const slowTimer = setTimeout(onSlow, 2500);
  try {
    while (Date.now() - started < timeoutMs) {
      try {
        const res = await fetch(apiUrl("/api/health"), { cache: "no-store", signal: AbortSignal.timeout(20_000) });
        if (res.ok) return true;
      } catch {
        /* still starting */
      }
      await new Promise((r) => setTimeout(r, 2000));
    }
    return false;
  } finally {
    clearTimeout(slowTimer);
  }
}
