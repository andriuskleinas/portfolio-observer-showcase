import { useEffect, useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";

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
  const themeIcon = { auto: "◐", light: "☀", dark: "☾" }[theme];

  return (
    <>
      <header className="topbar">
        <NavLink to="/" className="brand">
          <img src="/icon.svg" alt="" />
          <span className="hide-sm">Portfolio Observer</span>
        </NavLink>
        <nav className="nav" aria-label="Main">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="topbar-actions">
          <button
            className="ghost icon-btn"
            aria-pressed={privacy}
            title={privacy ? "Show amounts" : "Hide amounts (privacy mode)"}
            onClick={() => setPrivacy(!privacy)}
          >
            {privacy ? "◉" : "◎"}
            <span className="hide-sm">{privacy ? "Hidden" : "Amounts"}</span>
          </button>
          <button className="ghost icon-btn" title={`Theme: ${theme}`} onClick={() => setTheme(nextTheme[theme])}>
            {themeIcon}
          </button>
        </div>
      </header>
      <main>{children}</main>
    </>
  );
}
