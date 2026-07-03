import {
  Bot,
  CalendarDays,
  GitFork,
  Mail,
  MessageSquare,
  MessagesSquare,
  PanelsTopLeft,
} from "lucide-react";

export type SandboxStatus = "Ready" | "Running" | "Needs attention";

export type Sandbox = {
  id: string;
  name: string;
  repo: string;
  branch: string;
  status: SandboxStatus;
  twins: string[];
  workflowCount: number;
  lastRun: string;
};

export type TwinOption = {
  id: string;
  name: string;
  version: string;
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

export const twinOptions: TwinOption[] = [
  {
    id: "github",
    name: "GitHub",
    version: "v3",
    description: "Repositories, issues, pull requests, and checks.",
    tone: "bg-neutral-900",
  },
  {
    id: "slack",
    name: "Slack",
    version: "v1",
    description: "Channels, messages, threads, and summaries.",
    tone: "bg-emerald-500",
  },
  {
    id: "gmail",
    name: "Gmail",
    version: "v1",
    description: "Inbox search, messages, drafts, and send flows.",
    tone: "bg-red-500",
  },
  {
    id: "stripe",
    name: "Stripe",
    version: "2022-11-15",
    description: "Customers, payment intents, refunds, and events.",
    tone: "bg-violet-500",
  },
  {
    id: "google-calendar",
    name: "Google Calendar",
    version: "v3",
    description: "Events, attendees, calendars, and availability.",
    tone: "bg-blue-500",
  },
  {
    id: "hubspot",
    name: "HubSpot",
    version: "v3",
    description: "Contacts, companies, deals, and CRM state.",
    tone: "bg-orange-500",
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
  default: MessageSquare,
};
