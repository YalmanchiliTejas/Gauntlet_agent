import * as React from "react";

import { SettingsWorkspace } from "@/components/settings-workspace";

export default function SettingsPage() {
  return (
    <React.Suspense>
      <SettingsWorkspace />
    </React.Suspense>
  );
}
