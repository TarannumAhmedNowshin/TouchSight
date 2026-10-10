import { ShownIssue } from "@/lib/types";

type Props = {
  issues: ShownIssue[];
  onFocus: (index: number | null) => void;
  onSelect: (index: number) => void;
};

export default function IssueList({ issues, onFocus, onSelect }: Props) {
  if (issues.length === 0) {
    return (
      <ul className="issues">
        <li className="none">No problems found. Every shape, gap and label meets the size rules.</li>
      </ul>
    );
  }
  return (
    <ul className="issues">
      {issues.map((x, i) => (
        <li
          key={i}
          className={x.phase === "fixed" ? "fixed" : x.severity}
          data-at={x.at ? i : undefined}
          onMouseEnter={() => x.at && onFocus(i)}
          onMouseLeave={() => onFocus(null)}
          onClick={() => x.at && onSelect(i)}
        >
          {x.message}
          <small>
            {x.phase === "fixed" ? `Fixed: ${x.fix}` : x.severity === "error" ? "Needs a person to check" : "Worth a look"}
          </small>
        </li>
      ))}
    </ul>
  );
}
