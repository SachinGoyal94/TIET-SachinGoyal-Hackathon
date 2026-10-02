import { labelColor } from "../lib/format";

export default function LabelPill({ label }: { label: string }) {
  const color = labelColor(label);
  return (
    <span className="pill" style={{ backgroundColor: `${color}22`, color }}>
      {label}
    </span>
  );
}
