import * as React from "react";

import { RunsWorkspace } from "@/components/runs-workspace";

export default function RunsPage() {
  return (
    <React.Suspense>
      <RunsWorkspace />
    </React.Suspense>
  );
}
