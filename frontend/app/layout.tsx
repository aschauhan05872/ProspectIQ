import type { ReactNode } from "react";
import "./globals.css";

export const metadata = {
  title: "ProspectIQ",
  description: "AI Lead Intelligence Engine — internal V0",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
