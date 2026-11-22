import type { Metadata, Viewport } from "next";
import { Instrument_Sans, JetBrains_Mono } from "next/font/google";
import { Header, NextStep } from "@/components/Header";
import { SceneProvider } from "@/components/SceneProvider";
import { getSource } from "@/lib/source";
import "./globals.css";

const sans = Instrument_Sans({ subsets: ["latin"], axes: ["wdth"], variable: "--font-sans", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", display: "swap" });

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: { default: "backdate", template: "%s | backdate" },
  description:
    "Bitemporal facts for Django on Postgres. Correct a fact in the past and only the results that read it are recomputed.",
};

export const viewport: Viewport = { themeColor: "#0d1124", colorScheme: "dark" };

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const source = await getSource();
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body>
        <SceneProvider source={source}>
          <Header />
          <main id="main">
            {children}
            <NextStep />
          </main>
        </SceneProvider>
      </body>
    </html>
  );
}
