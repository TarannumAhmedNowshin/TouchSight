"use client";

import { useEffect, useState } from "react";
import { Result, TEX_NAMES } from "@/lib/types";

type Props = {
  result: Result;
  original: string;
  busy: boolean;
  onRebuild: (exclude: string[]) => void;
};

/** Shows what the model kept and left out, and lets a teacher drop parts and rebuild instantly. */
export default function PartsEditor({ result, original, busy, onRebuild }: Props) {
  const [excluded, setExcluded] = useState<Set<string>>(new Set());

  useEffect(() => {
    setExcluded(new Set(result.elements.filter((e) => e.excluded_by_teacher).map((e) => e.id)));
  }, [result]);

  const toggle = (id: string) =>
    setExcluded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const current = new Set(result.elements.filter((e) => e.excluded_by_teacher).map((e) => e.id));
  const changed = excluded.size !== current.size || [...excluded].some((id) => !current.has(id));
  const keptCount = result.elements.length - excluded.size;

  return (
    <div>
      <div className="read-grid">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <figure><img src={original} alt="Original diagram" /><figcaption>Original</figcaption></figure>
        {result.segmentation_png && (
          <figure>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={`data:image/png;base64,${result.segmentation_png}`} alt="Outlines traced from the original" />
            <figcaption>Traced shapes</figcaption>
          </figure>
        )}
      </div>
      <div className="read-lists">
        <div>
          <h3>Parts on the page</h3>
          <p className="hint">Untick anything a student doesn&apos;t need, then rebuild. No new model call is made.</p>
          <ul className="parts">
            {result.elements.map((e) => (
              <li key={e.id}>
                <label>
                  <input type="checkbox" checked={!excluded.has(e.id)} onChange={() => toggle(e.id)} disabled={busy} />
                  <span>
                    <b>{e.name}</b> <span aria-hidden="true" className="br">{e.braille}</span>
                    <small>
                      {e.reason}
                      {e.texture && e.texture !== "none" ? `. Felt as ${TEX_NAMES[e.texture]}.` : ""}
                      {!e.included && !e.excluded_by_teacher ? " Couldn't be traced cleanly." : ""}
                    </small>
                  </span>
                </label>
              </li>
            ))}
          </ul>
          <button className="btn primary rebuild" disabled={!changed || busy || keptCount === 0}
            onClick={() => onRebuild([...excluded])}>
            {busy ? "Rebuilding…" : "Rebuild page"}
          </button>
        </div>
        <div>
          <h3>Left out by the model</h3>
          <ul>
            {result.dropped.length ? result.dropped.map((x, i) => (
              <li key={i}><b>{x.what}</b><small>{x.reason}</small></li>
            )) : <li>Nothing</li>}
          </ul>
        </div>
      </div>
    </div>
  );
}
