import type { Metadata, Viewport } from "next";
import { Archivo } from "next/font/google";
import { Header, NextStep } from "@/components/Header";
import { SceneProvider } from "@/components/SceneProvider";
import { SourceNote } from "@/components/SourceNote";
import { getSource } from "@/lib/source";
import "./globals.css";

const archivo = Archivo({ subsets: ["latin"], axes: ["wdth"], variable: "--font-archivo", display: "swap" });

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: { default: "backdate", template: "%s | backdate" },
  description:
    "Bitemporal facts for Django on Postgres. Correct a fact in the past and only the results that read it are recomputed.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#edf1e7" },
    { media: "(prefers-color-scheme: dark)", color: "#1a2140" },
  ],
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const source = await getSource();
  return (
    <html lang="en" className={archivo.variable}>
      <body>
        <SceneProvider source={source}>
          <Header />
          <SourceNote />
          <main id="main">
            {children}
            <NextStep />
          </main>
        </SceneProvider>
      </body>
    </html>
  );
}
