import type { ReactNode } from "react";
import type { Metadata } from "next";
import "./globals.css";
import { Space_Grotesk } from "next/font/google";
import { AppShell } from "./components/AppShell";

const grotesk = Space_Grotesk({
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600", "700"]
});

export const metadata: Metadata = {
  title: "todometry",
  description: "Local-first activity analytics, project history, and automations."
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={grotesk.className}>
      <body suppressHydrationWarning>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
