import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { Meta, Num } from "../api";
import { money, pct, tone } from "../format";
import { IconArrowDown, IconArrowUp } from "./Icons";

// --- data loading ----------------------------------------------------------------

/** Loads data and keeps the previous result on screen while refetching. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    fn()
      .then((d) => alive && (setData(d), setError(null)))
      .catch((e: Error) => alive && setError(e.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}

export const MetaContext = createContext<Meta | null>(null);
export function useMeta(): Meta {
  const m = useContext(MetaContext);
  if (!m) throw new Error("Meta not loaded");
  return m;
}

export function useClassLabel() {
  const meta = useMeta();
  return (key: string) => (key === "cash" ? "Cash" : meta.asset_classes.find((c) => c.key === key)?.label ?? key);
}

// --- figures -----------------------------------------------------------------------

export function Money({ v, ccy, compact, signed, decimals, className = "" }: {
  v: Num | undefined; ccy: string; compact?: boolean; signed?: boolean; decimals?: number; className?: string;
}) {
  return <span className={`money ${className}`}>{money(v, ccy, { compact, signed, decimals })}</span>;
}

/** Signed change with arrow + color; the arrow keeps direction readable without color. */
export function Delta({ v, ccy, percent, pill }: { v: Num | undefined; ccy?: string; percent?: boolean; pill?: boolean }) {
  const text = percent ? pct(v, { signed: true }) : money(v, ccy ?? "USD", { signed: true });
  const t = tone(v);
  return (
    <span className={`delta ${t} ${pill ? "pill" : ""} ${percent ? "" : "money"}`}>
      {t === "up" && <IconArrowUp size={pill ? 13 : 12} className="delta-icon" />}
      {t === "down" && <IconArrowDown size={pill ? 13 : 12} className="delta-icon" />}
      {text}
    </span>
  );
}

/** Stable color per asset class, shared by allocation bars and holding avatars. */
export function classColor(key: string) {
  return `var(--c-${key.replace(/_/g, "-")}, var(--c-other))`;
}

export function AssetAvatar({ name, symbol, assetClass }: { name: string; symbol?: string | null; assetClass: string }) {
  const src = (symbol && symbol.length <= 5 ? symbol : name).replace(/[^A-Za-z0-9]/g, "");
  const initials = src.slice(0, symbol && symbol.length <= 5 ? 3 : 2).toUpperCase() || "•";
  return (
    <span className="avatar" style={{ ["--av" as string]: classColor(assetClass) }} aria-hidden="true">
      {initials}
    </span>
  );
}

export function StatTile({ label, children, sub }: { label: string; children: ReactNode; sub?: ReactNode }) {
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{children}</div>
      {sub && <div className="tile-sub">{sub}</div>}
    </div>
  );
}

export function ErrorBox({ error }: { error: string | null | undefined }) {
  if (!error) return null;
  return (
    <div className="error-box" role="alert">
      {error}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <h2>{title}</h2>
      {children}
    </div>
  );
}

// --- dialogs and fields --------------------------------------------------------------

export function Modal({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog ref={ref} onClose={onClose} onCancel={onClose}>
      {open && (
        <div className="dialog-body">
          <div className="dialog-head">
            <h2>{title}</h2>
            <button className="ghost icon-btn" onClick={onClose} aria-label="Close">
              ✕
            </button>
          </div>
          {children}
        </div>
      )}
    </dialog>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="field">
      {label}
      {children}
      {hint && <span className="muted">{hint}</span>}
    </label>
  );
}

export function SortHeader<K extends string>({ k, label, sort, setSort, className = "" }: {
  k: K; label: string; sort: { key: K; dir: 1 | -1 }; setSort: (s: { key: K; dir: 1 | -1 }) => void; className?: string;
}) {
  const active = sort.key === k;
  return (
    <th
      className={`sortable ${className}`}
      aria-sort={active ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
      onClick={() => setSort({ key: k, dir: active ? ((-sort.dir) as 1 | -1) : -1 })}
    >
      {label}
      {active ? (sort.dir === 1 ? " ↑" : " ↓") : ""}
    </th>
  );
}
