import type { ReactNode } from "react";
import type { Metadata } from "next";
import "./globals.css";
import "./fonts/space-grotesk.css";
import { AppShell } from "./components/AppShell";

export const metadata: Metadata = {
  title: "todometry",
  description: "Local-first Todoist dashboard for activity analytics and project history."
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body suppressHydrationWarning>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
