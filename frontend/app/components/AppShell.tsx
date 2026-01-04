"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_GROUPS = [
  {
    title: "Core",
    items: [
      { href: "/", label: "Overview", hint: "Summary and highlights" },
      { href: "/analytics", label: "Analytics", hint: "Plots and trends" },
      { href: "/llm-agent-chat", label: "LLM-Agent Chat", hint: "Local chat (beta)" }
    ]
  },
  {
    title: "Automation Studio",
    items: [
      { href: "/task-rollout-rules", label: "Task Rollout Rules", hint: "LLM breakdown prompts" },
      { href: "/task-templates", label: "Task Templates", hint: "Create and edit templates" },
      { href: "/multiplication-labels", label: "Multiplication Labels", hint: "Tune Xn effects" }
    ]
  },
  {
    title: "Operations",
    items: [
      { href: "/control-panel", label: "Control Panel", hint: "Runs, logs, and status" }
    ]
  }
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname.startsWith(href);
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

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
          <p className="muted tiny">Tip: use labels like <strong>llm-breakdown</strong> or <strong>template-feature</strong>.</p>
        </div>
      </aside>

      <div className="appMain">
        <main className="page">{children}</main>
      </div>
    </div>
  );
}
