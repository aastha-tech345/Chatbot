"use client";
import { useState } from "react";
import { Eye } from "lucide-react";
import { LogEntry } from "@/types";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/common/status-badge";
import { Dialog } from "@/components/ui/dialog";

/** Pure data table — no filters, no tabs, no pagination inside. */
export function LogTable({ logs }: { logs: LogEntry[] }) {
  const [active, setActive] = useState<LogEntry | null>(null);

  return (
    <>
      <div className="overflow-x-auto">
        <table className="data-table w-full min-w-[800px]">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Level</th>
              <th>Application</th>
              <th>Source</th>
              <th>Message</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr key={log.id}>
                <td className="whitespace-nowrap font-mono text-xs text-muted-foreground">{log.timestamp}</td>
                <td><StatusBadge status={log.level} /></td>
                <td className="font-medium text-foreground">{log.application}</td>
                <td className="text-muted-foreground">{log.source}</td>
                <td className="max-w-[240px] truncate text-muted-foreground">{log.message}</td>
                <td>
                  <span className={
                    log.status.includes("200")
                      ? "text-xs font-medium text-success"
                      : log.status.includes("4") || log.status.includes("5")
                        ? "text-xs font-medium text-destructive"
                        : "text-xs text-muted-foreground"
                  }>
                    {log.status}
                  </span>
                </td>
                <td>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => setActive(log)}
                    aria-label="View log details"
                  >
                    <Eye className="h-3.5 w-3.5" />
                  </Button>
                </td>
              </tr>
            ))}
            {logs.length === 0 && (
              <tr>
                <td colSpan={7} className="py-2">
                  <div className="flex flex-col items-center py-10">
                    <svg viewBox="0 0 200 140" fill="none" className="h-24 w-auto mb-3" aria-hidden="true">
                      <rect width="200" height="140" rx="12" fill="hsl(220 18% 97%)"/>
                      {[28,44,60,76,92,108].map((y,i) => (
                        <rect key={y} x="24" y={y} width={i===2?152:90+i*8} height="8" rx="4"
                          fill={i===0?"hsl(252 84% 57% / 0.2)":"hsl(220 12% 88%)"}/>
                      ))}
                      <circle cx="148" cy="94" r="26" fill="white" stroke="hsl(220 16% 88%)" strokeWidth="1.5"/>
                      <circle cx="148" cy="94" r="14" fill="none" stroke="hsl(252 84% 57% / 0.35)" strokeWidth="2.5"/>
                      <path d="M158 104 L168 114" stroke="hsl(252 84% 57% / 0.5)" strokeWidth="3" strokeLinecap="round"/>
                    </svg>
                    <p className="text-sm text-muted-foreground">No log entries found.</p>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <Dialog open={Boolean(active)} title="Log Details" onClose={() => setActive(null)}>
        <div className="space-y-2.5">
          {active && Object.entries(active).map(([k, v]) =>
            v !== undefined ? (
              <div key={k} className="flex gap-3 text-sm">
                <span className="w-28 shrink-0 font-medium capitalize text-muted-foreground">{k}</span>
                <span className="break-all text-foreground">{String(v)}</span>
              </div>
            ) : null
          )}
        </div>
      </Dialog>
    </>
  );
}
