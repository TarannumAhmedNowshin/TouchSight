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

export type Element = {
  id: string;
  name: string;
  kind: string;
  importance: number;
  texture: string | null;
  reason: string;
  method: string;
  braille: string;
};

export type Result = {
  job: string;
  title: string;
  title_braille: string;
  summary: string;
  diagram_type: string;
  provider: string;
  mask_status?: string;
  elements: Element[];
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
};

export type Sample = { name: string; url: string; label: string };

export const TEX_NAMES: Record<string, string> = {
  dots: "dots",
  diagonal: "diagonal lines",
  crosshatch: "crosshatch",
  horizontal: "horizontal lines",
  vertical: "vertical lines",
  grid: "grid",
};
