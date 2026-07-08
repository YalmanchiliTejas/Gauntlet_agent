import * as React from "react";

import { RunDetail } from "@/components/run-detail";

export default async function RunDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <React.Suspense>
      <RunDetail id={id} />
    </React.Suspense>
  );
}
