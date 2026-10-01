"use client";
import Link from "next/link";
import { Eye, Pencil, Trash2 } from "lucide-react";
import { Application } from "@/types";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/common/status-badge";
import { Dialog } from "@/components/ui/dialog";
import { useState, useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateApplicationStatus } from "@/lib/api/applications";
import { toast } from "sonner";
import { SearchableSelect } from "@/components/ui/searchable-select";

const STATUSES = ["Active", "Inactive", "Testing"];

/** Pure data table — no search, no pagination. Those live in the page. */
export function ApplicationTable({
  apps,
  onDelete,
  loading = false,
}: {
  apps: Application[];
  onDelete: (id: string) => void;
  loading?: boolean;
}) {
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [statusUpdate, setStatusUpdate] = useState<{ id: string; status: string } | null>(null);
  const qc = useQueryClient();
  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      updateApplicationStatus(id, status),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["applications"] });
      toast.success("Status updated successfully");
      setStatusUpdate(null);
    },
    onError: () => {
      toast.error("Failed to update status");
    },
  });

  const handleStatusChange = (appId: string, newStatus: string, currentStatus: string) => {
    if (newStatus !== currentStatus) {
      setStatusUpdate({ id: appId, status: newStatus });
    }
  };

  return (
    <>
      <div className="overflow-x-auto">
        <table className="data-table w-full min-w-[760px]">
          <thead>
            <tr>
              <th>Application</th>
              <th>App ID</th>
              <th>Type</th>
              <th>Base URL</th>
              <th>Status</th>
              <th>Routes</th>
              <th>Updated</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {apps.map((app) => (
              <tr key={app.id}>
                <td className="font-medium text-foreground">{app.name}</td>
                <td className="font-mono text-xs text-muted-foreground">{app.appId}</td>
                <td className="text-muted-foreground">{app.type}</td>
                <td>
                  <span className="block max-w-[160px] truncate font-mono text-xs text-muted-foreground">
                    {app.baseUrl}
                  </span>
                </td>
                {/* <td className="w-[140px]">
                  <SearchableSelect
                    value={app.status}
                    onChange={(newStatus) => handleStatusChange(app.id, newStatus, app.status)}
                    options={STATUSES.map((status) => ({ value: status, label: status }))}
                    placeholder="Select..."
                  />
                </td> */}
                <td
                  className={`font-medium ${app.status === "Active"
                      ? "text-green-600"
                      : app.status === "Inactive"
                        ? "text-red-600"
                        : app.status === "Testing"
                          ? "text-yellow-600"
                          : "text-muted-foreground"
                    }`}
                >
                  {app.status}
                </td>
                <td className="text-muted-foreground">{app.routes}</td>
                <td className="text-muted-foreground">{app.updatedAt.split(" ")[0]}</td>
                <td>
                  <div className="flex items-center gap-0.5">
                    <Button asChild variant="ghost" size="icon-sm" aria-label="View">
                      <Link href={`/app-registry/${app.id}`}><Eye className="h-3.5 w-3.5" /></Link>
                    </Button>
                    <Button asChild variant="ghost" size="icon-sm" aria-label="Edit">
                      <Link href={`/app-registry/${app.id}/edit`}><Pencil className="h-3.5 w-3.5" /></Link>
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label="Delete"
                      onClick={() => setDeleteId(app.id)}
                      className="text-destructive hover:bg-[hsl(var(--destructive-bg))] hover:text-destructive"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
            {apps.length === 0 && (
              <tr>
                <td colSpan={8} className="py-2">
                  <div className="flex flex-col items-center py-10">
                    <svg viewBox="0 0 200 160" fill="none" className="h-24 w-auto mb-3" aria-hidden="true">
                      <rect width="200" height="160" rx="12" fill="hsl(252 84% 97%)" />
                      <rect x="30" y="48" width="60" height="72" rx="6" fill="white" stroke="hsl(252 84% 57% / 0.2)" strokeWidth="1.5" />
                      <rect x="40" y="62" width="40" height="6" rx="3" fill="hsl(252 84% 57% / 0.3)" />
                      <rect x="40" y="74" width="28" height="6" rx="3" fill="hsl(252 84% 57% / 0.15)" />
                      <path d="M90 84 H110" stroke="hsl(252 84% 57% / 0.4)" strokeWidth="1.5" strokeDasharray="3 3" />
                      <rect x="110" y="60" width="60" height="48" rx="8" fill="white" stroke="hsl(252 84% 57% / 0.25)" strokeWidth="1.5" />
                    </svg>
                    <p className="text-sm text-muted-foreground">No applications match your filters.</p>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <Dialog open={Boolean(deleteId)} title="Delete Application" onClose={() => setDeleteId(null)}>
        <p className="text-sm text-muted-foreground">
          This will permanently remove the application from the registry. This action cannot be undone.
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" onClick={() => setDeleteId(null)}>Cancel</Button>
          <Button
            variant="destructive"
            onClick={() => { if (deleteId) { onDelete(deleteId); setDeleteId(null); } }}
          >
            Delete
          </Button>
        </div>
      </Dialog>

      <Dialog
        open={Boolean(statusUpdate)}
        title="Confirm Status Change"
        onClose={() => setStatusUpdate(null)}
      >
        <p className="text-sm text-muted-foreground">
          Are you sure you want to change the status to <span className="font-medium text-foreground">{statusUpdate?.status}</span>?
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" onClick={() => setStatusUpdate(null)}>Cancel</Button>
          <Button
            onClick={() => {
              if (statusUpdate) {
                statusMutation.mutate({ id: statusUpdate.id, status: statusUpdate.status });
              }
            }}
            disabled={statusMutation.isPending}
          >
            {statusMutation.isPending ? "Updating..." : "Confirm"}
          </Button>
        </div>
      </Dialog>
    </>
  );
}
