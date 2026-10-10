export type Issue = {
  code: string;
  severity: "error" | "warning";
  message: string;
  ids: string[];
  at: [number, number] | null;
  fixed: boolean;
  fix: string;
};

export type KeyRow = { name: string; key: string | null; texture: string | null; kind: string };

export type Part = {
  id: string;
  name: string;
  kind: "region" | "line" | "point";
  importance: number;
  reason: string;
  braille: string;
  included: boolean;
  excluded_by_teacher: boolean;
  texture: string | null;
  method: string;
};

export type Result = {
  job: string;
  title: string;
  title_braille: string;
  summary: string;
  description: string;
  diagram_type: string;
  provider: string;
  elements: Part[];
  dropped: { what: string; reason: string }[];
  key: KeyRow[];
  validation: {
    before: { score: number; issues: Issue[] };
    after: { score: number; issues: Issue[] };
    fixes: string[];
  };
  svg_preview: string;
  heightmap_png: string;
  segmentation_png: string | null;
  timings: Record<string, number>;
  shapes: Shape[];
  tour: string[];
};

export type Shape = { id: string; name: string; spoken: string } & (
  | { type: "polygon"; points: [number, number][] }
  | { type: "lines"; lines: [number, number][][] }
  | { type: "point"; at: [number, number] }
);

export type Sample = { name: string; url: string; label: string };

export type ShownIssue = Issue & { phase: "fixed" | "open" };

export const TEX_NAMES: Record<string, string> = {
  dots: "dots",
  diagonal: "diagonal lines",
  crosshatch: "crosshatch",
  horizontal: "horizontal lines",
  vertical: "vertical lines",
  grid: "grid",
};
