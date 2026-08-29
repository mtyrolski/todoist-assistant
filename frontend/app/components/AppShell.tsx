"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { SURFACE_STATUS_SUMMARY } from "../lib/dashboardCopy";

const NAV_GROUPS = [
  {
    title: "Stable",
    items: [
      { href: "/", label: "Overview", hint: "Summary and highlights" }
    ]
  },
  {
    title: "Automation",
    items: [{ href: "/multiplication-labels", label: "Task Multiplication", hint: "Expand labelled work safely" }]
  },
  {
    title: "Operations",
    items: [
      { href: "/live-logs", label: "Live Logs", hint: "Read-only runtime inspection" },
      { href: "/control-panel", label: "Control Panel", hint: "Runs, settings, and status" }
    ]
  }
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname.startsWith(href);
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "";

  return (
    <div className="appShell">
      <aside className="sidebar">
        <Link className="brand" href="/">
          <span className="brandMark" aria-hidden>
            *
          </span>
          <div>
            <p className="brandTitle">Todoist Assistant</p>
            <p className="brandTag">Local insights, automations, and AI workflows</p>
          </div>
        </Link>

        <nav className="nav" aria-label="Primary">
          {NAV_GROUPS.map((group) => (
            <div key={group.title} className="navGroup">
              <p className="navTitle">{group.title}</p>
              <div className="navItems">
                {group.items.map((item) => {
                  const active = isActive(pathname, item.href);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={`navLink${active ? " navLinkActive" : ""}`}
                      aria-current={active ? "page" : undefined}
                    >
                      <span className="navLabel">{item.label}</span>
                      <span className="navHint">{item.hint}</span>
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        <div className="sidebarFooter">
          <p className="muted tiny">{SURFACE_STATUS_SUMMARY}</p>
        </div>
      </aside>

      <div className="appMain">
        <main className="page">{children}</main>
      </div>
    </div>
  );
}
