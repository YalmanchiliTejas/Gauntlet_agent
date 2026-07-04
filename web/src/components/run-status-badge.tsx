import { Badge } from "@/components/ui/badge";
import type { RunStatus } from "@/lib/sandbox-api";
import { cn } from "@/lib/utils";

const styles: Record<RunStatus, string> = {
  queued: "bg-slate-100 text-slate-700",
  running: "bg-blue-50 text-blue-700",
  passed: "bg-emerald-50 text-emerald-700",
  failed: "bg-red-50 text-red-700",
  error: "bg-amber-50 text-amber-700",
};

export function RunStatusBadge({ status }: { status: RunStatus }) {
  return (
    <Badge
      variant="secondary"
      className={cn("h-5 w-fit rounded-md px-1.5 text-[11px] font-medium capitalize", styles[status])}
    >
      {status}
    </Badge>
  );
}
