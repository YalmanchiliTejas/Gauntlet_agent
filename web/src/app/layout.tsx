import type { Metadata } from "next";
import { SandboxStoreProvider } from "@/components/sandbox-store";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

export const metadata: Metadata = {
  title: "Gauntlet",
  description: "Sandboxed workflow testing for AI agents.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full bg-background text-foreground">
        <SandboxStoreProvider>
          <TooltipProvider>
            {children}
            <Toaster />
          </TooltipProvider>
        </SandboxStoreProvider>
      </body>
    </html>
  );
}
