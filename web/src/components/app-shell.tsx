"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Boxes,
  GitBranch,
  PanelLeftClose,
  PanelLeftOpen,
  PlayCircle,
  Settings,
  ShieldCheck,
  Wrench,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

const navItems = [
  { label: "Sandboxes", href: "/sandboxes", icon: Boxes },
  { label: "Workflows", href: "/workflows", icon: GitBranch },
  { label: "Runs", href: "/runs", icon: PlayCircle },
  { label: "Fixes", href: "/fixes", icon: Wrench },
  { label: "Settings", href: "/settings", icon: Settings },
];

type AppShellProps = {
  children: React.ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useLocalCollapsedState();

  return (
    <div className="min-h-screen bg-background text-foreground">
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-30 hidden border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-[width] duration-200 md:flex md:flex-col",
          collapsed ? "w-[72px]" : "w-64",
        )}
      >
        <div className="flex h-16 items-center gap-3 px-4">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <ShieldCheck className="size-4" />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <div className="text-sm font-semibold text-foreground">Gauntlet</div>
              <div className="text-xs text-muted-foreground">Agent sandboxes</div>
            </div>
          )}
        </div>

        <Separator />

        <nav className="flex flex-1 flex-col gap-1 p-3">
          {navItems.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                title={collapsed ? item.label : undefined}
                className={cn(
                  "flex h-9 items-center rounded-lg text-sm font-medium transition-colors",
                  collapsed ? "justify-center px-0" : "gap-3 px-3",
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground shadow-sm"
                    : "text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                )}
              >
                <Icon className="size-4 shrink-0" />
                {!collapsed && <span>{item.label}</span>}
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-sidebar-border p-3">
          <Button
            type="button"
            variant="ghost"
            size={collapsed ? "icon" : "default"}
            className={cn("w-full", !collapsed && "justify-start")}
            title={collapsed ? "Expand navigation" : "Collapse navigation"}
            onClick={() => setCollapsed(!collapsed)}
          >
            {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
            {!collapsed && <span>Collapse</span>}
          </Button>
        </div>
      </aside>

      <div
        className={cn(
          "min-h-screen transition-[padding] duration-200",
          collapsed ? "md:pl-[72px]" : "md:pl-64",
        )}
      >
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b bg-background/95 px-4 backdrop-blur md:hidden">
          <div className="flex items-center gap-2">
            <div className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <ShieldCheck className="size-4" />
            </div>
            <span className="text-sm font-semibold">Gauntlet</span>
          </div>
        </header>
        {children}
      </div>
    </div>
  );
}

function useLocalCollapsedState() {
  const [collapsed, setCollapsed] = React.useState(() => {
    if (typeof window === "undefined") {
      return false;
    }
    return window.localStorage.getItem("gauntlet-sidebar-collapsed") === "true";
  });

  const update = React.useCallback((next: boolean) => {
    setCollapsed(next);
    if (typeof window !== "undefined") {
      window.localStorage.setItem("gauntlet-sidebar-collapsed", String(next));
    }
  }, []);

  return [collapsed, update] as const;
}
