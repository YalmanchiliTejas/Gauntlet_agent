import * as React from "react";

import { SandboxesWorkspace } from "@/components/sandboxes-workspace";

export default function SandboxesPage() {
  return (
    <React.Suspense>
      <SandboxesWorkspace />
    </React.Suspense>
  );
}
