"use client";

import type { ReactNode } from "react";
import "./globals.css";
import { Space_Grotesk } from "next/font/google";

const grotesk = Space_Grotesk({
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600", "700"]
});

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={grotesk.className}>
      <body>{children}</body>
    </html>
  );
}
