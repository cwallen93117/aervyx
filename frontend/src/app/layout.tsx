import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "FlightComp Platform",
  description: "Competition scoring for hang gliding and paragliding",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}