"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import { Issue, Result, Sample, TEX_NAMES } from "@/lib/types";

const Relief = dynamic(() => import("@/components/Relief"), { ssr: false });

const STEPS = [
  { id: "understand", title: "Understand", text: "A vision model decides what a student needs and what to leave out." },
  { id: "segment", title: "Trace", text: "Each kept part is cut out of the image and turned into clean outlines." },
  { id: "design", title: "Design for touch", text: "Textures, dead zones and braille labels follow tactile-graphics guidelines." },
  { id: "export", title: "Check and export", text: "A readability check fixes what it can, then builds print and 3D files." },
];
type Tab = "page" | "relief" | "read";
type ShownIssue = Issue & { phase: "fixed" | "open" };

export default function Home() {
  const [samples, setSamples] = useState<Sample[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [orig, setOrig] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(-1); // index of active step while busy
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("page");
  const [ink, setInk] = useState(true);
  const [hot, setHot] = useState<number | null>(null);
  const [over, setOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch("/api/samples").then((r) => r.json()).then(setSamples).catch(() => {});
  }, []);

  const convert = useCallback(async (fd: FormData, origUrl: string) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setStep(0);
    // the server runs every stage in one request; walk the list while we wait
    const timer = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 1800);
    try {
      const res = await fetch("/api/convert", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Conversion failed. Try again or use a different image.");
      setOrig(origUrl);
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

  const sendFile = (f: File) => {
    if (!f.type.startsWith("image/")) return setError("That file isn't an image. Use a PNG, JPG or WebP.");
    setSelected(null);
    const fd = new FormData();
    fd.append("file", f);
    convert(fd, URL.createObjectURL(f));
  };

  const runSample = (s: Sample) => {
    setSelected(s.name);
    const fd = new FormData();
    fd.append("sample", s.name);
    convert(fd, s.url);
  };

  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const f = [...(e.clipboardData?.files || [])].find((x) => x.type.startsWith("image/"));
      if (f) sendFile(f);
    };
    document.addEventListener("paste", onPaste);
    return () => document.removeEventListener("paste", onPaste);
  });

  const issues: ShownIssue[] = result
    ? [
        ...result.validation.before.issues.filter((x) => x.fixed).map((x) => ({ ...x, phase: "fixed" as const })),
        ...result.validation.after.issues.map((x) => ({ ...x, phase: "open" as const })),
      ]
    : [];

  const stepState = (i: number) => {
    if (busy) return i < step ? "done" : i === step ? "active" : "";
    return result ? "done" : "";
  };

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
                  <button key={s.name} className="sample" aria-pressed={selected === s.name} onClick={() => runSample(s)} disabled={busy}>
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

        <section className="stage" aria-live="polite">
          <div className="tabs" role="tablist">
            {(["page", "relief", "read"] as Tab[]).map((t) => (
              <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>
                {t === "page" ? "Tactile page" : t === "relief" ? "3D relief" : "How it was read"}
              </button>
            ))}
            <label className="toggle">
              <input type="checkbox" checked={ink} onChange={(e) => setInk(e.target.checked)} /> Print labels for helpers
            </label>
          </div>

          {tab === "page" && (
            <div className={`sheet${busy ? " busy" : ""}${ink ? "" : " ink-off"}`}>
              {result ? (
                <>
                  <div className="svg-host" role="img" aria-label={`Tactile graphic: ${result.title}. ${result.summary}`}
                    dangerouslySetInnerHTML={{ __html: result.svg_preview }} />
                  <svg className="markers" viewBox="0 0 297 210" aria-hidden="true">
                    {issues.map((x, i) => x.at && (
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

          {tab === "relief" && (result ? <Relief heightmap={result.heightmap_png} /> :
            <div className="relief"><p className="relief-hint">Convert a diagram first to see its raised surface.</p></div>)}

          {tab === "read" && result && (
            <div>
              <div className="read-grid">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <figure><img src={orig} alt="Original diagram" /><figcaption>Original</figcaption></figure>
                {result.segmentation_png && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <figure><img src={`data:image/png;base64,${result.segmentation_png}`} alt="Shapes the pipeline traced" />
                    <figcaption>Traced shapes</figcaption></figure>
                )}
              </div>
              <div className="read-lists">
                <div>
                  <h3>Kept</h3>
                  <ul>
                    {result.elements.map((e) => (
                      <li key={e.id}><b>{e.name}</b> <span aria-hidden="true">{e.braille}</span>
                        <small>{e.reason}{e.texture && e.texture !== "none" ? `, ${TEX_NAMES[e.texture]}` : ""}</small></li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h3>Left out</h3>
                  <ul>
                    {result.dropped.length ? result.dropped.map((x, i) => (
                      <li key={i}><b>{x.what}</b><small>{x.reason}</small></li>
                    )) : <li>Nothing</li>}
                  </ul>
                </div>
              </div>
            </div>
          )}
          {tab === "read" && !result && <p className="meta">Convert a diagram first.</p>}

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
                <ul className="issues">
                  {issues.length === 0 && (
                    <li className="none">No problems found. Every shape, gap and label meets the size rules.</li>
                  )}
                  {issues.map((x, i) => (
                    <li key={i} className={x.phase === "fixed" ? "fixed" : x.severity}
                      data-at={x.at ? i : undefined}
                      onMouseEnter={() => x.at && setHot(i)} onMouseLeave={() => setHot(null)}
                      onClick={() => { if (x.at) { setTab("page"); setHot(i); } }}>
                      {x.message}
                      <small>{x.phase === "fixed" ? `Fixed: ${x.fix}` : x.severity === "error" ? "Needs a person to check" : "Worth a look"}</small>
                    </li>
                  ))}
                </ul>
              </section>
              <section className="keybox">
                <h2>Key</h2>
                <ul>
                  {result.key.map((row) => (
                    <li key={row.name}>
                      <span className="k">{row.key ?? ""}</span>
                      <span className="b" aria-hidden="true">{result.elements.find((e) => e.name === row.name)?.braille}</span>
                      <small>{row.name}{row.texture ? `, ${TEX_NAMES[row.texture]}` : ""}</small>
                    </li>
                  ))}
                </ul>
                <h2 className="dl-h">Download</h2>
                <div className="downloads">
                  <a className="btn primary" href={`/api/download/${result.job}/svg`} download>Print file for swell paper (SVG)</a>
                  <a className="btn" href={`/api/download/${result.job}/stl`} download>3D-print file (STL)</a>
                  <a className="btn ghost" href={`/api/download/${result.job}/heightmap`} download>Height map (PNG)</a>
                </div>
                <p className="meta">
                  Read by {result.provider}. Diagram type: {result.diagram_type}. {result.elements.length} parts kept,{" "}
                  {result.dropped.length} left out.
                </p>
              </section>
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
