/**
 * Dependency-free SVG charts.
 *
 * The previous "charts" were absolutely-sized <div>s with a pixel height, which is why
 * they read as coloured blocks: no axis, no grid, no baseline, no shared scale. These
 * draw real coordinate-space SVG instead, sized by viewBox so they stay sharp and
 * responsive without pulling in a charting library.
 *
 * Colours come from the scheme: blue shades, orange #FF9800 for warnings,
 * grid #E9EDF5.
 */

import { useId, useMemo, useState } from "react";

export const SERIES_COLORS = {
  purple: "#1D4ED8",
  blue: "#1677FF",
  orange: "#FF9800",
  green: "#2563EB",
  red: "#EF4444",
};

const GRID = "#E9EDF5";
const AXIS_TEXT = "#8490AE";

/* ---------------------------------------------------------------- helpers -- */

export function formatCompact(value) {
  const number = Number(value || 0);
  if (Math.abs(number) >= 1_000_000) return `${(number / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (Math.abs(number) >= 1_000) return `${(number / 1_000).toFixed(1).replace(/\.0$/, "")}K`;
  return String(Math.round(number * 100) / 100);
}

/** Catmull-Rom through the points, converted to cubic beziers, so the line is smooth. */
function smoothPath(points) {
  if (points.length < 2) return points.length ? `M ${points[0].x} ${points[0].y}` : "";
  let d = `M ${points[0].x} ${points[0].y}`;
  for (let i = 0; i < points.length - 1; i += 1) {
    const p0 = points[i - 1] || points[i];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[i + 2] || p2;
    const c1x = p1.x + (p2.x - p0.x) / 6;
    const c1y = p1.y + (p2.y - p0.y) / 6;
    const c2x = p2.x - (p3.x - p1.x) / 6;
    const c2y = p2.y - (p3.y - p1.y) / 6;
    d += ` C ${c1x} ${c1y}, ${c2x} ${c2y}, ${p2.x} ${p2.y}`;
  }
  return d;
}

function niceCeiling(value) {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  return Math.ceil(value / magnitude) * magnitude;
}

/* ------------------------------------------------------------- area chart -- */

/**
 * `series`: [{ key, name, color, area? }]
 * `data`:   [{ label, [key]: number }]
 */
export function AreaChart({ data = [], series = [], height = 240, formatValue = formatCompact, yTicks = 4 }) {
  const gradientId = useId();
  const [hover, setHover] = useState(null);

  const W = 720;
  const H = height;
  const pad = { top: 16, right: 16, bottom: 30, left: 46 };
  const plotW = W - pad.left - pad.right;
  const plotH = H - pad.top - pad.bottom;

  const max = useMemo(() => {
    const values = data.flatMap((row) => series.map((s) => Number(row[s.key] || 0)));
    return niceCeiling(Math.max(...values, 0) || 1);
  }, [data, series]);

  if (!data.length) {
    return (
      <div className="grid h-[200px] place-items-center rounded-xl bg-surface text-sm text-muted">
        Not enough data to chart yet.
      </div>
    );
  }

  const xAt = (i) => pad.left + (data.length === 1 ? plotW / 2 : (i / (data.length - 1)) * plotW);
  const yAt = (v) => pad.top + plotH - (Number(v || 0) / max) * plotH;

  const ticks = Array.from({ length: yTicks + 1 }, (_, i) => (max / yTicks) * i);

  return (
    <div className="w-full">
      {/* Uniform scaling: preserveAspectRatio="none" would stretch the axis text and
          stroke widths with the container, so the viewBox ratio drives the height. */}
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-auto w-full"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(event) => {
          const box = event.currentTarget.getBoundingClientRect();
          const ratio = ((event.clientX - box.left) / box.width) * W;
          const index = Math.round(((ratio - pad.left) / plotW) * (data.length - 1));
          setHover(Math.min(data.length - 1, Math.max(0, index)));
        }}
      >
        <defs>
          {series.map((s) => (
            <linearGradient key={s.key} id={`${gradientId}-${s.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={s.color} stopOpacity="0.28" />
              <stop offset="100%" stopColor={s.color} stopOpacity="0" />
            </linearGradient>
          ))}
        </defs>

        {/* horizontal grid + y labels */}
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={pad.left} x2={W - pad.right} y1={yAt(tick)} y2={yAt(tick)} stroke={GRID} strokeWidth="1" />
            <text x={pad.left - 8} y={yAt(tick) + 4} textAnchor="end" fontSize="11" fill={AXIS_TEXT} fontWeight="600">
              {formatValue(tick)}
            </text>
          </g>
        ))}

        {/* x labels */}
        {data.map((row, i) => (
          <text key={row.label ?? i} x={xAt(i)} y={H - 9} textAnchor="middle" fontSize="11" fill={AXIS_TEXT} fontWeight="600">
            {row.label}
          </text>
        ))}

        {/* hover guide */}
        {hover !== null ? (
          <line x1={xAt(hover)} x2={xAt(hover)} y1={pad.top} y2={pad.top + plotH} stroke={GRID} strokeWidth="2" />
        ) : null}

        {series.map((s) => {
          const points = data.map((row, i) => ({ x: xAt(i), y: yAt(row[s.key]) }));
          const line = smoothPath(points);
          const area = `${line} L ${points[points.length - 1].x} ${pad.top + plotH} L ${points[0].x} ${pad.top + plotH} Z`;
          return (
            <g key={s.key}>
              {s.area === false ? null : <path d={area} fill={`url(#${gradientId}-${s.key})`} />}
              <path d={line} fill="none" stroke={s.color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
              {points.map((p, i) => (
                <circle
                  key={`${s.key}-${i}`}
                  cx={p.x}
                  cy={p.y}
                  r={hover === i ? 5 : 3}
                  fill="#FFFFFF"
                  stroke={s.color}
                  strokeWidth="2.5"
                />
              ))}
            </g>
          );
        })}
      </svg>

      {/* legend + read-out */}
      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-line-soft pt-3">
        {series.map((s) => (
          <span key={s.key} className="inline-flex items-center gap-2 text-xs font-bold text-muted">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: s.color }} />
            {s.name}
            {hover !== null ? (
              <span className="font-extrabold text-ink">{formatValue(data[hover][s.key])}</span>
            ) : null}
          </span>
        ))}
        {hover !== null ? <span className="ml-auto text-xs font-bold text-subtle">{data[hover].label}</span> : null}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ donut/ring -- */

export function ProgressRing({ value = 0, label, caption, color = SERIES_COLORS.purple, size = 112 }) {
  const pct = Math.max(0, Math.min(100, Number(value) || 0));
  const stroke = 10;
  const r = (size - stroke) / 2;
  const circumference = 2 * Math.PI * r;
  return (
    <div className="flex flex-col items-center text-center">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={GRID} strokeWidth={stroke} />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={color}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={circumference - (pct / 100) * circumference}
            style={{ transition: "stroke-dashoffset 600ms ease" }}
          />
        </svg>
        <div className="absolute inset-0 grid place-items-center">
          <span className="text-xl font-extrabold text-ink">{pct}%</span>
        </div>
      </div>
      <div className="mt-2 text-sm font-bold text-ink">{label}</div>
      {caption ? <div className="mt-0.5 text-[11px] leading-4 text-subtle">{caption}</div> : null}
    </div>
  );
}

/* --------------------------------------------------------- ranked bar list -- */

export function RankedBarList({ items = [], formatValue = formatCompact, color = SERIES_COLORS.purple }) {
  const max = Math.max(...items.map((i) => Number(i.value || 0)), 1);
  return (
    <ol className="space-y-3">
      {items.map((item, index) => (
        <li key={item.id ?? item.name}>
          <div className="flex items-center gap-3">
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-surface text-xs font-extrabold text-muted">
              {index + 1}
            </span>
            <span className="min-w-0 flex-1 truncate text-sm font-bold text-ink">{item.name}</span>
            <span className="shrink-0 text-sm font-extrabold text-ink">{formatValue(item.value)}</span>
          </div>
          <div className="mt-1.5 ml-10 flex items-center gap-3">
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-[#E9EDF5]">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{ width: `${Math.max(3, (Number(item.value || 0) / max) * 100)}%`, background: color }}
              />
            </div>
            {item.caption ? <span className="shrink-0 text-[11px] font-semibold text-subtle">{item.caption}</span> : null}
          </div>
        </li>
      ))}
    </ol>
  );
}

/* ---------------------------------------------------------------- sparkline -- */

export function Sparkline({ values = [], color = SERIES_COLORS.purple, width = 96, height = 32 }) {
  if (values.length < 2) return null;
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const points = values.map((v, i) => ({
    x: (i / (values.length - 1)) * width,
    y: height - ((v - min) / span) * height,
  }));
  return (
    <svg width={width} height={height} className="overflow-visible">
      <path d={smoothPath(points)} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
