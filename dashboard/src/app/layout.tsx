import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Sidebar, MobileSidebar } from "@/components/sidebar";
import { ThemeProvider } from "@/components/theme-provider";
import { ThemeToggle } from "@/components/theme-toggle";
import { Toaster } from "@/components/ui/sonner";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "agenticEvolve — Command Center",
  description: "agenticEvolve dashboard and monitoring",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <ThemeProvider defaultTheme="dark">
          <div className="flex h-screen overflow-hidden">
            <Sidebar />
            <div className="flex flex-1 flex-col overflow-hidden">
              {/* Header */}
              <header className="flex h-12 shrink-0 items-center justify-between border-b bg-card px-4">
                <div className="flex items-center gap-2">
                  <MobileSidebar />
                  <span className="text-xs font-medium text-muted-foreground">
                    Command Center v3.0
                  </span>
                </div>
                <ThemeToggle />
              </header>
              {/* Main content */}
              <main className="flex-1 overflow-y-auto p-4 md:p-6">
                {children}
              </main>
            </div>
          </div>
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  );
}
