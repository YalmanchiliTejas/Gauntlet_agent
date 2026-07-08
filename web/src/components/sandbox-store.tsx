"use client";

import * as React from "react";
import type { Sandbox } from "@/lib/mock-data";

// In-memory store lifted above the router so state survives tab navigation
// (the root layout doesn't unmount on client-side route changes). Not durable:
// a full reload resets it — real persistence needs the backend / Supabase.
type SandboxStore = {
  // Created + seeded sandboxes. null = not loaded yet this session.
  sandboxes: Sandbox[] | null;
  setSandboxes: React.Dispatch<React.SetStateAction<Sandbox[] | null>>;
  // Create-form draft, preserved while the user hops between tabs.
  sandboxName: string;
  setSandboxName: React.Dispatch<React.SetStateAction<string>>;
  repo: string;
  setRepo: React.Dispatch<React.SetStateAction<string>>;
  branch: string;
  setBranch: React.Dispatch<React.SetStateAction<string>>;
  selectedTwins: Record<string, string>;
  setSelectedTwins: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  repoQuery: string;
  setRepoQuery: React.Dispatch<React.SetStateAction<string>>;
};

const Ctx = React.createContext<SandboxStore | null>(null);

export function SandboxStoreProvider({ children }: { children: React.ReactNode }) {
  const [sandboxes, setSandboxes] = React.useState<Sandbox[] | null>(null);
  const [sandboxName, setSandboxName] = React.useState("");
  const [repo, setRepo] = React.useState("");
  const [branch, setBranch] = React.useState("main");
  const [selectedTwins, setSelectedTwins] = React.useState<Record<string, string>>({});
  const [repoQuery, setRepoQuery] = React.useState("");

  return (
    <Ctx.Provider
      value={{
        sandboxes,
        setSandboxes,
        sandboxName,
        setSandboxName,
        repo,
        setRepo,
        branch,
        setBranch,
        selectedTwins,
        setSelectedTwins,
        repoQuery,
        setRepoQuery,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useSandboxStore() {
  const store = React.useContext(Ctx);
  if (!store) throw new Error("useSandboxStore must be used within SandboxStoreProvider");
  return store;
}
