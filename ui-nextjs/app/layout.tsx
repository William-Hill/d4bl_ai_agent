import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "D4BL AI Agent - Research Tool | Data for Black Lives",
  description:
    "Data for Black Lives Research & Analysis Tool - Using data to create concrete and measurable change in the lives of Black people",
  icons: {
    icon: [
      { url: "/favicon.png", type: "image/png", sizes: "128x128" },
      { url: "/favicon.ico", type: "image/x-icon" },
    ],
    apple: [{ url: "/favicon.png", type: "image/png", sizes: "128x128" }],
    shortcut: "/favicon.ico",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-[#292929]`}
      >
        <nav className="border-b border-[#404040] bg-[#1a1a1a] px-6 py-3 flex items-center gap-8">
          <span className="font-bold text-[#00ff32] text-lg tracking-tight">
            D4BL
          </span>
          <Link
            href="/"
            className="text-sm text-gray-300 hover:text-[#00ff32] transition-colors"
          >
            Research
          </Link>
          <Link
            href="/explore"
            className="text-sm text-gray-300 hover:text-[#00ff32] transition-colors"
          >
            Explore Data
          </Link>
        </nav>
        {children}
      </body>
    </html>
  );
}
