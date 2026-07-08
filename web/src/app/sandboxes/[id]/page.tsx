import * as React from "react";

import { SandboxDetail } from "@/components/sandbox-detail";

export default async function SandboxDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <React.Suspense>
      <SandboxDetail id={id} />
    </React.Suspense>
  );
}
