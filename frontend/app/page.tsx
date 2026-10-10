"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import IssueList from "@/components/IssueList";
import KeyPanel from "@/components/KeyPanel";
import PartsEditor from "@/components/PartsEditor";
import * as api from "@/lib/api";
import { Result, Sample, ShownIssue } from "@/lib/types";

const Relief = dynamic(() => import("@/components/Relief"), { ssr: false });

const STEPS = [
  { id: "understand", title: "Understand", text: "A vision model decides what a student needs and what to leave out." },
  { id: "segment", title: "Trace", text: "Each kept part is cut out of the image and turned into clean outlines." },
  { id: "design", title: "Design for touch", text: "Textures, dead zones and braille labels follow tactile-graphics guidelines." },
  { id: "export", title: "Check and export", text: "A readability check fixes what it can, then builds print and 3D files." },
];
const TABS = [
  { id: "page", label: "Tactile page" },
  { id: "relief", label: "3D relief" },
  { id: "parts", label: "Parts" },
] as const;
type Tab = (typeof TABS)[number]["id"];

export default function Home() {
  const [samples, setSamples] = useState<Sample[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [original, setOriginal] = useState("");
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(-1);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("page");
  const [ink, setInk] = useState(true);
  const [hot, setHot] = useState<number | null>(null);
  const [over, setOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.listSamples().then(setSamples).catch(() => setSamples([]));
  }, []);

  /** Run a request while walking the step list (the server does every stage in one call). */
  const run = useCallback(async (work: () => Promise<Result>, originalUrl?: string) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setStep(0);
    const timer = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 1800);
    try {
      const data = await work();
      if (originalUrl) setOriginal(originalUrl);
      setResult(data);
      setHot(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      clearInterval(timer);
      setStep(-1);
      setBusy(false);
    }
  }, [busy]);

  const sendFile = useCallback((file: File) => {
    if (!file.type.startsWith("image/")) {
      setError("That file isn't an image. Use a PNG, JPG or WebP.");
      return;
    }
    setSelected(null);
    run(() => api.convert({ file }), URL.createObjectURL(file));
  }, [run]);

  const runSample = (s: Sample) => {
    setSelected(s.name);
    run(() => api.convert({ sample: s.name }), s.url);
  };

  const rebuild = (exclude: string[]) => {
    if (result) run(() => api.redesign(result.job, exclude));
  };

  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const file = [...(e.clipboardData?.files || [])].find((x) => x.type.startsWith("image/"));
      if (file) sendFile(file);
    };
    document.addEventListener("paste", onPaste);
    return () => document.removeEventListener("paste", onPaste);
  }, [sendFile]);

  const issues: ShownIssue[] = result
    ? [
        ...result.validation.before.issues.filter((x) => x.fixed).map((x) => ({ ...x, phase: "fixed" as const })),
        ...result.validation.after.issues.map((x) => ({ ...x, phase: "open" as const })),
      ]
    : [];

  const stepState = (i: number) => (busy ? (i < step ? "done" : i === step ? "active" : "") : result ? "done" : "");

  return (
    <>
      <header className="top">
        <div className="brand">
          <h1>TouchSight</h1>
          <span className="brand-braille" aria-hidden="true">⠞⠕⠥⠉⠓⠎⠊⠛⠓⠞</span>
        </div>
        <p className="lede">
          Turn a textbook diagram into a tactile graphic a blind student can read with their fingers: simplified shapes,
          distinct textures, braille labels, ready to print on swell paper or 3D-print.
        </p>
      </header>

      <main className="layout">
        <aside className="input">
          <label
            className={`drop${over ? " over" : ""}`}
            tabIndex={0}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileRef.current?.click(); } }}
            onDragEnter={(e) => { e.preventDefault(); setOver(true); }}
            onDragOver={(e) => { e.preventDefault(); setOver(true); }}
            onDragLeave={() => setOver(false)}
            onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) sendFile(f); }}
          >
            <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden
              onChange={(e) => { const f = e.target.files?.[0]; if (f) sendFile(f); e.target.value = ""; }} />
            <span className="drop-dots" aria-hidden="true">⠊⠍⠁⠛⠑</span>
            <strong>Drop a diagram here</strong>
            <span>or choose a file (PNG, JPG, WebP). You can also paste one.</span>
          </label>

          {samples.length > 0 && (
            <section className="samples" aria-labelledby="samples-h">
              <h2 id="samples-h">Or try a sample</h2>
              <div className="sample-row">
                {samples.map((s) => (
                  <button key={s.name} className="sample" aria-pressed={selected === s.name}
                    onClick={() => runSample(s)} disabled={busy}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={s.url} alt="" />
                    <span>{s.label}</span>
                  </button>
                ))}
              </div>
            </section>
          )}

          <section className="steps" aria-labelledby="steps-h">
            <h2 id="steps-h">How it works</h2>
            <ol>
              {STEPS.map((s, i) => (
                <li key={s.id} className={stepState(i)}>
                  <b>{s.title}</b>
                  <span>{s.text}</span>
                  <em>{!busy && result ? `${result.timings[s.id] ?? 0}s` : ""}</em>
                </li>
              ))}
            </ol>
          </section>
        </aside>

        <section className="stage" aria-live="polite" aria-busy={busy}>
          <div className="tabs" role="tablist">
            {TABS.map((t) => (
              <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}>{t.label}</button>
            ))}
            <label className="toggle">
              <input type="checkbox" checked={ink} onChange={(e) => setInk(e.target.checked)} /> Print labels for helpers
            </label>
          </div>

          {tab === "page" && (
            <div className={`sheet${busy ? " busy" : ""}${ink ? "" : " ink-off"}`}>
              {result ? (
                <>
                  {/* SVG is generated server-side from sanitised data only (see touchsight/export.py) */}
                  <div className="svg-host" role="img" aria-label={`Tactile graphic: ${result.description}`}
                    dangerouslySetInnerHTML={{ __html: result.svg_preview }} />
                  <svg className="markers" viewBox="0 0 297 210" aria-hidden="true">
                    {issues.map((x, i) => x.at && (x.phase === "open" || hot === i) && (
                      <circle key={i} cx={x.at[0]} cy={x.at[1]} r={5}
                        className={`marker${x.phase === "fixed" ? " fixed" : ""}${hot === i ? " on" : ""}`} />
                    ))}
                  </svg>
                </>
              ) : (
                <div className="empty">
                  <p className="empty-braille" aria-hidden="true">⠞⠗⠽ ⠁ ⠎⠁⠍⠏⠇⠑</p>
                  <p>Pick a sample or drop in your own diagram. You&apos;ll get an A4 tactile page here in a few seconds.</p>
                </div>
              )}
            </div>
          )}

          {tab === "relief" && (result ? <Relief heightmap={result.heightmap_png} /> : (
            <div className="relief"><p className="relief-hint">Convert a diagram first to see its raised surface.</p></div>
          ))}

          {tab === "parts" && (result
            ? <PartsEditor result={result} original={original} busy={busy} onRebuild={rebuild} />
            : <p className="meta">Convert a diagram first.</p>)}

          {error && <p className="error" role="alert">{error}</p>}

          {result && (
            <div className="results">
              <section className="check">
                <h2>Readability check</h2>
                <div className="score">
                  <div><span className="num">{result.validation.before.score}</span><span className="cap">first draft</span></div>
                  <span className="arrow" aria-hidden="true" />
                  <div><span className="num after">{result.validation.after.score}</span><span className="cap">after auto-fix</span></div>
                </div>
                <IssueList issues={issues} onFocus={setHot} onSelect={(i) => { setTab("page"); setHot(i); }} />
              </section>
              <KeyPanel result={result} />
            </div>
          )}
        </section>
      </main>

      <footer className="foot">
        <p>
          Follows published tactile-graphics guidance: shapes at least ¼ inch, ⅛ inch between elements, distinct
          neighbouring textures, braille labels with a key. A draft for a qualified transcriber to review, not a
          replacement for one.
        </p>
      </footer>
    </>
  );
}
