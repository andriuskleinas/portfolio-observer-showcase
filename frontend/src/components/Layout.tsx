import { useEffect, useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { BrandMark, IconAuto, IconEye, IconEyeOff, IconLock, IconMoon, IconSun } from "./Icons";

type Theme = "auto" | "light" | "dark";

function readPref<T extends string>(key: string, fallback: T): T {
  try {
    return (localStorage.getItem(key) as T) || fallback;
  } catch {
    return fallback;
  }
}

function writePref(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private mode: preference just isn't remembered */
  }
}

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/transactions", label: "Transactions" },
  { to: "/accounts", label: "Accounts" },
  { to: "/assets", label: "Assets" },
  { to: "/import", label: "Import" },
  { to: "/status", label: "Status" },
];

export function Layout({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => readPref("theme", "auto"));
  const [privacy, setPrivacy] = useState<boolean>(() => readPref<string>("privacy", "0") === "1");

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "auto") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    writePref("theme", theme);
  }, [theme]);

  useEffect(() => {
    document.body.classList.toggle("privacy", privacy);
    writePref("privacy", privacy ? "1" : "0");
  }, [privacy]);

  const nextTheme: Record<Theme, Theme> = { auto: "light", light: "dark", dark: "auto" };
  const ThemeIcon = { auto: IconAuto, light: IconSun, dark: IconMoon }[theme];
  const themeName = { auto: "System", light: "Light", dark: "Dark" }[theme];

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <NavLink to="/" className="brand" aria-label="Portfolio Observer — dashboard">
            <BrandMark />
            <span className="brand-name hide-sm">
              Portfolio <span>Observer</span>
            </span>
          </NavLink>
          <nav className="nav" aria-label="Main">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end}>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="topbar-actions">
            <span className="trust-badge hide-md" title="Your data is stored in a local database on this computer and is never sent to a cloud service.">
              <IconLock size={14} />
              Local &amp; private
            </span>
            <button
              className="ghost icon-btn"
              aria-pressed={privacy}
              aria-label={privacy ? "Show amounts" : "Hide amounts"}
              title={privacy ? "Show amounts" : "Hide amounts (privacy mode)"}
              onClick={() => setPrivacy(!privacy)}
            >
              {privacy ? <IconEyeOff /> : <IconEye />}
            </button>
            <button
              className="ghost icon-btn"
              aria-label={`Theme: ${themeName}. Switch theme`}
              title={`Theme: ${themeName}`}
              onClick={() => setTheme(nextTheme[theme])}
            >
              <ThemeIcon />
            </button>
          </div>
        </div>
      </header>
      <main>{children}</main>
      <footer className="footer">
        <span><IconLock size={12} /> Data stays on this device · no tracking, no third-party analytics</span>
        <span>Portfolio Observer · for information only, not investment advice</span>
      </footer>
    </>
  );
}
