import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

export interface LineSeries {
  name: string;
  color: string; // CSS color, usually var(--series-n)
  points: { date: string; y: number }[];
  area?: boolean;
  step?: boolean; // hold each value until the next point (manual valuations)
}

export interface Marker {
  date: string;
  y: number;
  color: string;
  label: string;
}

interface Props {
  series: LineSeries[];
  markers?: Marker[];
  markerLegend?: { label: string; color: string }[];
  height?: number;
  zeroBaseline?: boolean;
  formatY: (v: number) => string;
  formatValue: (v: number) => string;
  ariaLabel: string;
}

const M = { top: 10, right: 12, bottom: 26, left: 58 };

function niceStep(range: number, target: number) {
  const raw = range / Math.max(1, target);
  const mag = 10 ** Math.floor(Math.log10(raw || 1));
  const norm = raw / mag;
  return (norm >= 5 ? 10 : norm >= 2 ? 5 : norm >= 1 ? 2 : 1) * mag;
}

const toTime = (d: string) => new Date(`${d}T00:00:00`).getTime();

/** Line/area chart: 2px lines, 10% area wash, hairline grid, crosshair + tooltip
 *  that lists every series at the hovered date. Keyboard: focus, then ← →. */
export function LineChart({ series, markers = [], markerLegend = [], height = 260, zeroBaseline, formatY, formatValue, ariaLabel }: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(240, Math.floor(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const base = series[0]?.points ?? [];
  const geo = useMemo(() => {
    const times = base.map((p) => toTime(p.date));
    const all = series.flatMap((s) => s.points.map((p) => p.y)).concat(markers.map((m) => m.y));
    let lo = Math.min(...all, zeroBaseline ? 0 : Infinity);
    let hi = Math.max(...all);
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) {
      lo = 0;
      hi = 1;
    }
    if (lo === hi) hi = lo + (Math.abs(lo) || 1);
    const step = niceStep(hi - lo, 4);
    lo = Math.floor(lo / step) * step;
    hi = Math.ceil(hi / step) * step;
    const ticks: number[] = [];
    for (let v = lo; v <= hi + step / 2; v += step) ticks.push(v);
    const t0 = times[0] ?? 0;
    const t1 = times[times.length - 1] ?? 1;
    const iw = width - M.left - M.right;
    const ih = height - M.top - M.bottom;
    const x = (t: number) => M.left + (t1 === t0 ? iw / 2 : ((t - t0) / (t1 - t0)) * iw);
    const y = (v: number) => M.top + ih - ((v - lo) / (hi - lo)) * ih;
    return { times, ticks, x, y, t0, t1, lo };
  }, [series, markers, base, width, height, zeroBaseline]);

  const xTicks = useMemo(() => {
    const { t0, t1 } = geo;
    const spanDays = (t1 - t0) / 86400000;
    const n = Math.max(2, Math.min(6, Math.floor(width / 110)));
    const out: { t: number; label: string }[] = [];
    for (let i = 0; i < n; i++) {
      const t = t0 + ((t1 - t0) * i) / (n - 1);
      const d = new Date(t);
      const label = spanDays > 400
        ? d.toLocaleDateString(undefined, { month: "short", year: "2-digit" })
        : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
      out.push({ t, label });
    }
    return out;
  }, [geo, width]);

  if (base.length === 0) {
    return <div className="empty muted">No data for this period</div>;
  }

  const path = (pts: { date: string; y: number }[], step = false) =>
    pts
      .map((p, i) => {
        const x = geo.x(toTime(p.date)).toFixed(1);
        const y = geo.y(p.y).toFixed(1);
        if (i === 0) return `M${x},${y}`;
        return step ? `H${x}V${y}` : `L${x},${y}`;
      })
      .join("");

  const nearest = (px: number) => {
    let best = 0;
    let bestD = Infinity;
    geo.times.forEach((t, i) => {
      const d = Math.abs(geo.x(t) - px);
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    });
    return best;
  };

  const onMove = (e: PointerEvent<SVGRectElement>) => {
    const r = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
    setHover(nearest(e.clientX - r.left));
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowLeft") setHover((h) => Math.max(0, (h ?? base.length) - 1));
    else if (e.key === "ArrowRight") setHover((h) => Math.min(base.length - 1, (h ?? -1) + 1));
    else if (e.key === "Escape") setHover(null);
    else return;
    e.preventDefault();
  };

  const hx = hover !== null ? geo.x(geo.times[hover]) : 0;
  const hoverDate = hover !== null ? base[hover].date : null;
  const markersAt = hoverDate ? markers.filter((m) => m.date === hoverDate) : [];
  const legend = series.length > 1 || markerLegend.length > 0;
  const baselineY = geo.y(Math.max(geo.lo, 0));

  return (
    <div className="chart" ref={wrap}>
      {legend && (
        <div className="legend" aria-hidden="true">
          {series.map((s) => (
            <span key={s.name}>
              <i className="key-line" style={{ background: s.color }} />
              {s.name}
            </span>
          ))}
          {markerLegend.map((m) => (
            <span key={m.label}>
              <i className="key-dot" style={{ background: m.color }} />
              {m.label}
            </span>
          ))}
        </div>
      )}
      <svg width={width} height={height} role="img" aria-label={ariaLabel}>
        {geo.ticks.map((v) => (
          <g key={v}>
            <line x1={M.left} x2={width - M.right} y1={geo.y(v)} y2={geo.y(v)} stroke="var(--grid)" strokeWidth={1} />
            <text className="money" x={M.left - 8} y={geo.y(v)} dy="0.32em" textAnchor="end">
              {formatY(v)}
            </text>
          </g>
        ))}
        {xTicks.map((t, i) => (
          <text key={i} x={geo.x(t.t)} y={height - 6} textAnchor={i === 0 ? "start" : i === xTicks.length - 1 ? "end" : "middle"}>
            {t.label}
          </text>
        ))}
        <line x1={M.left} x2={width - M.right} y1={baselineY} y2={baselineY} stroke="var(--axis)" strokeWidth={1} />
        {series.map((s) =>
          s.area ? (
            <path
              key={`a-${s.name}`}
              d={`${path(s.points, s.step)}L${geo.x(toTime(s.points[s.points.length - 1].date))},${baselineY}L${geo.x(toTime(s.points[0].date))},${baselineY}Z`}
              fill={s.color}
              opacity={0.1}
            />
          ) : null,
        )}
        {series.map((s) => (
          <path key={s.name} d={path(s.points, s.step)} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        ))}
        {markers.map((m, i) => (
          <circle key={i} cx={geo.x(toTime(m.date))} cy={geo.y(m.y)} r={4.5} fill={m.color} stroke="var(--surface)" strokeWidth={2} />
        ))}
        {hover !== null && (
          <g pointerEvents="none">
            <line x1={hx} x2={hx} y1={M.top} y2={height - M.bottom} stroke="var(--axis)" strokeWidth={1} />
            {series.map((s) => {
              const p = s.points[hover];
              return p ? <circle key={s.name} cx={hx} cy={geo.y(p.y)} r={4} fill={s.color} stroke="var(--surface)" strokeWidth={2} /> : null;
            })}
          </g>
        )}
        <rect
          x={M.left}
          y={M.top}
          width={Math.max(0, width - M.left - M.right)}
          height={height - M.top - M.bottom}
          fill="transparent"
          tabIndex={0}
          aria-label={`${ariaLabel}. Use left and right arrow keys to read values.`}
          onPointerMove={onMove}
          onPointerLeave={() => setHover(null)}
          onFocus={() => setHover((h) => h ?? base.length - 1)}
          onBlur={() => setHover(null)}
          onKeyDown={onKey}
        />
      </svg>
      {hover !== null && (
        <div
          className="tooltip"
          style={{ left: Math.min(Math.max(hx + 12, 0), width - 190), top: M.top }}
          role="status"
        >
          <div className="tt-date">{new Date(geo.times[hover]).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}</div>
          {series.map((s) =>
            s.points[hover] ? (
              <div className="tt-row" key={s.name}>
                <i className="key-line" style={{ background: s.color }} />
                <strong className="money">{formatValue(s.points[hover].y)}</strong>
                <span className="name">{s.name}</span>
              </div>
            ) : null,
          )}
          {markersAt.map((m, i) => (
            <div className="tt-row" key={i}>
              <i className="key-dot" style={{ background: m.color }} />
              <span className="name">{m.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
