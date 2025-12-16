import type { ReactNode } from "react";
import type { Metadata } from "next";
import "./globals.css";
import { Space_Grotesk } from "next/font/google";

const grotesk = Space_Grotesk({
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600", "700"]
});

export const metadata: Metadata = {
  title: "Todoist Assistant Dashboard",
  description: "A fast, dark dashboard for Todoist Assistant"
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={grotesk.className}>
      <body>{children}</body>
    </html>
  );
}
