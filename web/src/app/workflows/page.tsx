import * as React from "react";

import { WorkflowsWorkspace } from "@/components/workflows-workspace";

export default function WorkflowsPage() {
  return (
    <React.Suspense>
      <WorkflowsWorkspace />
    </React.Suspense>
  );
}
