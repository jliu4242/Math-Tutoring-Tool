import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MathFlow AI",
  description: "AI-powered math tutoring companion for content generation, lesson design, and diagnostic grading.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
