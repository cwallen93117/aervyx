import "./globals.css";
import "maplibre-gl/dist/maplibre-gl.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "Aervyx",
  description: "Open-source competition platform for hang gliding and paragliding",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Exo+2:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;0,900;1,700;1,800&family=Barlow:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
      </head>
      <body suppressHydrationWarning>
        <script src="https://accounts.google.com/gsi/client" async defer />
        {children}
      </body>
    </html>
  );
}
