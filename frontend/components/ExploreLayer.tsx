"use client";

import { useRef, useState } from "react";
import { Shape } from "@/lib/types";
import { speak } from "@/lib/speech";

type Props = { shapes: Shape[]; activeId: string | null; onActive: (id: string | null) => void };

/**
 * Invisible hit areas laid over the tactile page.
 *  - Tap a part: hear its full description.
 *  - Slide a finger (or mouse with the button held): hear each part's name as you cross it.
 *  - Keyboard: Tab between parts, Enter or Space to hear one.
 * Larger shapes are drawn first so smaller, nested parts sit on top and win the hit test.
 */
export default function ExploreLayer({ shapes, activeId, onActive }: Props) {
  const lastSlide = useRef<string | null>(null);
  const dragging = useRef(false);
  const [focusId, setFocusId] = useState<string | null>(null);

  const byId = (id: string | null) => shapes.find((s) => s.id === id);

  const announce = (id: string, full: boolean) => {
    const s = byId(id);
    if (!s) return;
    onActive(id);
    speak(full ? s.spoken : s.name);
  };

  const shapeAt = (x: number, y: number): string | null => {
    const el = document.elementFromPoint(x, y) as Element | null;
    return el?.closest("[data-part]")?.getAttribute("data-part") ?? null;
  };

  return (
    <svg
      className="explore"
      viewBox="0 0 297 210"
      role="group"
      aria-label="Touch and listen: tap a part to hear it, slide to hear names, or use Tab and Enter"
      onPointerDown={(e) => {
        dragging.current = true;
        const id = shapeAt(e.clientX, e.clientY);
        lastSlide.current = id;
        if (id) announce(id, true);
        else onActive(null);
      }}
      onPointerMove={(e) => {
        if (!dragging.current) return;
        const id = shapeAt(e.clientX, e.clientY);
        if (id && id !== lastSlide.current) {
          lastSlide.current = id;
          announce(id, false);
        }
      }}
      onPointerUp={() => { dragging.current = false; }}
      onPointerLeave={() => { dragging.current = false; }}
    >
      {shapes.map((s) => {
        const on = activeId === s.id || focusId === s.id;
        const common = {
          "data-part": s.id,
          className: `hit${on ? " on" : ""}`,
          tabIndex: 0,
          role: "button",
          "aria-label": s.spoken,
          onFocus: () => setFocusId(s.id),
          onBlur: () => setFocusId(null),
          onKeyDown: (e: React.KeyboardEvent) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              announce(s.id, true);
            }
          },
        };
        if (s.type === "polygon") {
          return <polygon key={s.id} {...common} points={s.points.map((p) => p.join(",")).join(" ")} />;
        }
        if (s.type === "lines") {
          return (
            <g key={s.id} {...common}>
              {s.lines.map((ln, i) => (
                <polyline key={i} points={ln.map((p) => p.join(",")).join(" ")} className="hit-line" />
              ))}
            </g>
          );
        }
        return <circle key={s.id} {...common} cx={s.at[0]} cy={s.at[1]} r={6} />;
      })}
    </svg>
  );
}
