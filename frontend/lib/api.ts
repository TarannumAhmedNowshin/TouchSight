import { Result, Sample } from "./types";

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
  return parse<Sample[]>(await fetch("/api/samples"), "Couldn't load samples.");
}

export async function convert(input: { file: File } | { sample: string }): Promise<Result> {
  const fd = new FormData();
  if ("file" in input) fd.append("file", input.file);
  else fd.append("sample", input.sample);
  const res = await fetch("/api/convert", { method: "POST", body: fd });
  return parse<Result>(res, "Conversion failed. Try again or use a different image.");
}

export async function redesign(job: string, exclude: string[]): Promise<Result> {
  const res = await fetch("/api/redesign", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job, exclude }),
  });
  return parse<Result>(res, "Couldn't rebuild the page.");
}
