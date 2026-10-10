"use client";

import { useState } from "react";
import { Result, TEX_NAMES } from "@/lib/types";

/** The braille key, the screen-reader description and the downloads. */
export default function KeyPanel({ result }: { result: Result }) {
  const [copied, setCopied] = useState(false);
  const brailleFor = (name: string) => result.elements.find((e) => e.name === name)?.braille;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(result.description);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard blocked: text stays selectable */
    }
  };

  return (
    <section className="keybox">
      <h2>Key</h2>
      <ul>
        {result.key.map((row) => (
          <li key={row.name}>
            <span className="k">{row.key ?? ""}</span>
            <span className="b" aria-hidden="true">{brailleFor(row.name)}</span>
            <small>{row.name}{row.texture ? `, ${TEX_NAMES[row.texture]}` : ""}</small>
          </li>
        ))}
      </ul>

      <h2>Description for screen readers</h2>
      <p className="description">{result.description}</p>
      <button className="btn ghost" onClick={copy}>{copied ? "Copied" : "Copy description"}</button>

      <h2 className="dl-h">Download</h2>
      <div className="downloads">
        <a className="btn primary" href={`/api/download/${result.job}/svg`} download>Print file for swell paper (SVG)</a>
        <a className="btn" href={`/api/download/${result.job}/stl`} download>3D-print file (STL)</a>
        <a className="btn ghost" href={`/api/download/${result.job}/heightmap`} download>Height map (PNG)</a>
      </div>
      <p className="meta">
        Read by {result.provider}. Diagram type: {result.diagram_type}.{" "}
        {result.elements.filter((e) => e.included).length} parts on the page, {result.dropped.length} left out by the model.
      </p>
    </section>
  );
}
