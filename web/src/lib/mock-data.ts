import {
  Bot,
  CalendarDays,
  GitFork,
  Mail,
  MessageSquare,
  MessagesSquare,
  PanelsTopLeft,
  Phone,
  Send,
  Table,
} from "lucide-react";

export type SandboxStatus = "Ready" | "Running" | "Needs attention";

export type Sandbox = {
  id: string;
  name: string;
  repo: string;
  branch: string;
  status: SandboxStatus;
  twins: string[];
  // service id -> pinned spec version (present for DB-backed sandboxes).
  twinVersions?: Record<string, string>;
  workflowCount: number;
  lastRun: string;
};

export type TwinOption = {
  id: string;
  name: string;
  // Available spec versions on disk (registry/<id>/<version>). Latest last —
  // matches the backend, which fills a missing version with versions[-1].
  versions: string[];
  description: string;
  tone: string;
};

export const initialSandboxes: Sandbox[] = [
  {
    id: "sandbox_steel_main",
    name: "Browser agent regression",
    repo: "acme/browser-agent",
    branch: "main",
    status: "Ready",
    twins: ["GitHub", "Slack", "Gmail"],
    workflowCount: 12,
    lastRun: "18 min ago",
  },
  {
    id: "sandbox_support_eval",
    name: "Support agent eval",
    repo: "acme/support-agent",
    branch: "release-candidate",
    status: "Running",
    twins: ["Stripe", "Gmail", "Slack"],
    workflowCount: 8,
    lastRun: "Running now",
  },
  {
    id: "sandbox_calendar_ops",
    name: "Calendar scheduling suite",
    repo: "acme/scheduler-agent",
    branch: "main",
    status: "Needs attention",
    twins: ["Google Calendar", "HubSpot"],
    workflowCount: 5,
    lastRun: "Yesterday",
  },
];

// The services we ship a twin for (gauntlet DOMAINS ∩ twins/registry). ids are
// the backend service keys; versions mirror the folders under registry/<id>/.
// ponytail: static fallback — the options route overlays the live backend
// catalog when connected; update this list when a registry version is added.
export const twinOptions: TwinOption[] = [
  {
    id: "github",
    name: "GitHub",
    versions: ["v3"],
    description: "Repositories, issues, pull requests, and checks.",
    tone: "bg-neutral-900",
  },
  {
    id: "slack",
    name: "Slack",
    versions: ["v1"],
    description: "Channels, messages, threads, and summaries.",
    tone: "bg-emerald-500",
  },
  {
    id: "gmail",
    name: "Gmail",
    versions: ["v1"],
    description: "Inbox search, messages, drafts, and send flows.",
    tone: "bg-red-500",
  },
  {
    id: "stripe",
    name: "Stripe",
    versions: ["2022-11-15"],
    description: "Customers, payment intents, refunds, and events.",
    tone: "bg-violet-500",
  },
  {
    id: "google_calendar",
    name: "Google Calendar",
    versions: ["v3"],
    description: "Events, attendees, calendars, and availability.",
    tone: "bg-blue-500",
  },
  {
    id: "hubspot",
    name: "HubSpot",
    versions: ["v3"],
    description: "Contacts, companies, deals, and CRM state.",
    tone: "bg-orange-500",
  },
  {
    id: "twilio",
    name: "Twilio",
    versions: ["2010-04-01"],
    description: "Messages, calls, and phone number lookups.",
    tone: "bg-rose-500",
  },
  {
    id: "resend",
    name: "Resend",
    versions: ["v1"],
    description: "Transactional email sending and delivery events.",
    tone: "bg-slate-800",
  },
  {
    id: "excel",
    name: "Excel",
    versions: ["v1"],
    description: "Workbooks, worksheets, ranges, and tables.",
    tone: "bg-green-600",
  },
];

// Mock workflows + runs for the signed-out / no-DB fallback, so the Workflows,
// Runs, and trace views are demoable in dev.
export const mockWorkflows = [
  {
    id: "wf_refund_flow",
    sandboxId: "sandbox_support_eval",
    name: "Refund a charge and email the customer",
    description: "Look up a payment in Stripe, refund it, then confirm via Gmail.",
    difficulty: "medium",
    taskPrompt:
      "The customer requests a refund. Find the payment intent in Stripe, create a refund, then email the customer via Gmail confirming it.",
    services: ["Stripe", "Gmail"],
    createdAt: "2026-06-30T12:00:00.000Z",
  },
];

export const mockRuns = [
  {
    id: "run_refund_1",
    sandboxId: "sandbox_support_eval",
    workflowId: "wf_refund_flow",
    workflowName: "Refund a charge and email the customer",
    fixOf: null,
    status: "failed" as const,
    trajectory: [
      { step: 1, tool: "stripe.paymentIntents.retrieve", status: "ok", detail: "pi_3Ka… found, amount $42.00" },
      { step: 2, tool: "stripe.refunds.create", status: "ok", detail: "re_1Nb… created for $42.00" },
      { step: 3, tool: "gmail.messages.send", status: "error", detail: "Missing recipient: customer email not carried forward from the charge" },
    ],
    verdict: { verdict: "fail", issues: ["Refund email never sent — recipient was not resolved from the Stripe customer."] },
    review: { findings: [] as { steps: number[]; axis: string; severity: "low" | "med" | "high"; title: string; recommendation?: string }[] },
    error: null,
    createdAt: "2026-07-01T09:15:00.000Z",
    finishedAt: "2026-07-01T09:15:22.000Z",
  },
];

export const repos = [
  {
    id: "repo_browser_agent",
    fullName: "acme/browser-agent",
    defaultBranch: "main",
  },
  {
    id: "repo_support_agent",
    fullName: "acme/support-agent",
    defaultBranch: "main",
  },
  {
    id: "repo_scheduler_agent",
    fullName: "acme/scheduler-agent",
    defaultBranch: "main",
  },
];

export const branchesByRepo: Record<string, { name: string; protected: boolean }[]> = {
  "acme/browser-agent": [
    { name: "main", protected: true },
    { name: "agent-loop", protected: false },
    { name: "browser-regression", protected: false },
  ],
  "acme/support-agent": [
    { name: "main", protected: true },
    { name: "release-candidate", protected: true },
    { name: "refund-workflows", protected: false },
  ],
  "acme/scheduler-agent": [
    { name: "main", protected: true },
    { name: "calendar-evals", protected: false },
  ],
};

export const twinIconMap = {
  GitHub: GitFork,
  Slack: MessagesSquare,
  Gmail: Mail,
  Stripe: PanelsTopLeft,
  "Google Calendar": CalendarDays,
  HubSpot: Bot,
  Twilio: Phone,
  Resend: Send,
  Excel: Table,
  default: MessageSquare,
};
