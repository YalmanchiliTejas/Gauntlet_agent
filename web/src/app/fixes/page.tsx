import * as React from "react";

import { FixesWorkspace } from "@/components/fixes-workspace";

export default function FixesPage() {
  return (
    <React.Suspense>
      <FixesWorkspace />
    </React.Suspense>
  );
}
