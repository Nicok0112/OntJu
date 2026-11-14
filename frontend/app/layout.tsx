import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LexEngine MX — Motor Ontológico Jurídico",
  description: "Auditoría normativa neuro-simbólica para despachos fiscales y corporativos.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es" className="dark">
      <body className="bg-slate-950 text-slate-100 antialiased">{children}</body>
    </html>
  );
}
