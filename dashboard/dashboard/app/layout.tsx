import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VoyageBlack — Incident Postmortem",
  description: "Automated postmortem generation from incident logs — powered by Elastic",
  icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-bg-base text-text-primary antialiased">
        <header className="border-b border-border-subtle bg-bg-surface">
          <div className="mx-auto max-w-7xl px-6 py-4 flex items-center gap-3">
            <a href="https://shipsafe-landing-o34wppiwiq-uc.a.run.app"
             className="font-mono text-xs text-text-tertiary hover:text-text-secondary transition-colors"
             style={{ textDecoration: 'none' }}>
            ← ShipSafe
          </a>
          <span className="text-border-strong">·</span>
          <div className="w-2 h-2 rounded-none bg-accent" />
            <span className="font-mono text-sm tracking-widest text-text-secondary uppercase">
              VoyageBlack
            </span>
            <span className="text-border-strong">·</span>
            <span className="text-xs text-text-tertiary">Incident Postmortem Engine</span>
            <div className="ml-auto flex items-center gap-2">
              <span className="font-mono text-xs text-signal-approve">● ELASTIC</span>
              <span className="font-mono text-xs text-text-tertiary">ELSER</span>
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-6 py-8">
          {children}
        </main>
      </body>
    </html>
  );
}
