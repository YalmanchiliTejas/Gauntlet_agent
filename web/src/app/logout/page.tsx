"use client";

import * as React from "react";
import { Loader2 } from "lucide-react";

import { signOut } from "@/lib/sandbox-api";

export default function LogoutPage() {
  React.useEffect(() => {
    signOut()
      .catch(() => {
        // Redirect even if the cookie is already gone.
      })
      .finally(() => {
        window.location.replace("/login");
      });
  }, []);

  return (
    <main className="flex min-h-screen items-center justify-center gap-3 text-muted-foreground">
      <Loader2 className="size-5 animate-spin" />
      <p className="text-sm">Clearing session...</p>
    </main>
  );
}
