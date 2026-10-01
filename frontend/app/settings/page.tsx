"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import WithLayout from "@/components/layout/with-layout";
import { PageHeader } from "@/components/common/page-header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { TabBorderBar, TabBorderButton } from "@/components/ui/tabs";
import { Dialog } from "@/components/ui/dialog";
import { Shield, Settings, Globe, Database, Bell } from "lucide-react";
import { changePassword } from "@/lib/api/settings";
import { useAuth } from "@/lib/auth-context";

const TABS = [
  { id: "General",    icon: Settings  },
  { id: "System",     icon: Database  },
  { id: "Security",   icon: Shield    },
  { id: "Appearance", icon: Globe     },
  { id: "Notifications", icon: Bell   },
];

export default function SettingsPage() {
  const router = useRouter();
  const { logout } = useAuth();
  const [tab, setTab] = useState("General");
  const [danger, setDanger] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isUpdatingPassword, setIsUpdatingPassword] = useState(false);

  const handlePasswordUpdate = async () => {
    if (!currentPassword || !newPassword || !confirmPassword) {
      toast.error("Please fill all password fields");
      return;
    }
    if (newPassword.length < 8) {
      toast.error("New password must be at least 8 characters");
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error("New password and confirm password do not match");
      return;
    }

    setIsUpdatingPassword(true);
    try {
      await changePassword({ currentPassword, newPassword });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      toast.success("Password updated successfully. Please log in again.");
      logout();
      router.replace("/login");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to update password");
    } finally {
      setIsUpdatingPassword(false);
    }
  };

  return (
    <WithLayout>
      <PageHeader title="Settings" subtitle="Manage system configuration and preferences" />

      <div className="grid gap-5 lg:grid-cols-[200px_1fr]">
        {/* Sidebar nav */}
        <Card className="h-fit p-2">
          <nav className="space-y-0.5">
            {TABS.map(({ id, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={`w-full flex items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm font-medium transition-colors ${
                  tab === id
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {id}
              </button>
            ))}
          </nav>
        </Card>

        {/* Content */}
        <div className="space-y-5">
          {tab === "General" && (
            <Card>
              <div className="border-b border-border px-5 py-4">
                <h2 className="text-sm font-semibold text-foreground">General Settings</h2>
                <p className="text-xs text-muted-foreground mt-0.5">Basic application configuration</p>
              </div>
              <div className="grid gap-4 p-5 md:grid-cols-2">
                <label className="grid gap-1.5">
                  <span className="text-xs font-semibold text-foreground">Application Name</span>
                  <Input defaultValue="Master Chatbot" />
                </label>
                <label className="grid gap-1.5">
                  <span className="text-xs font-semibold text-foreground">Default AI Provider</span>
                  <Select defaultValue="Groq">
                    <option>Groq</option>
                    <option>OpenAI</option>
                    <option>Google Gemini</option>
                  </Select>
                </label>
                <label className="grid gap-1.5">
                  <span className="text-xs font-semibold text-foreground">Default Model</span>
                  <Select defaultValue="llama-3.1-8b-instant">
                    <option>llama-3.1-8b-instant</option>
                    <option>gpt-4o-mini</option>
                  </Select>
                </label>
                <label className="grid gap-1.5">
                  <span className="text-xs font-semibold text-foreground">Backend URL</span>
                  <Input defaultValue="http://localhost:8000" />
                </label>
              </div>
              <div className="border-t border-border px-5 py-4">
                <p className="mb-3 text-xs font-semibold text-foreground">Feature Flags</p>
                <div className="space-y-2.5">
                  {[
                    { label: "Enable App Auto-Discovery", defaultChecked: true },
                    { label: "Show Debug Logs",           defaultChecked: false },
                  ].map(({ label, defaultChecked }) => (
                    <label key={label} className="flex items-center gap-2.5 cursor-pointer">
                      <input type="checkbox" defaultChecked={defaultChecked} className="h-4 w-4 rounded border-border accent-primary" />
                      <span className="text-sm text-foreground">{label}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div className="flex justify-end gap-2 border-t border-border px-5 py-4">
                <Button variant="outline">Reset</Button>
                <Button onClick={() => toast.success("Settings saved")}>Save Settings</Button>
              </div>
            </Card>
          )}

          {tab === "System" && (
            <Card>
              <div className="border-b border-border px-5 py-4">
                <h2 className="text-sm font-semibold text-foreground">System Information</h2>
              </div>
              <div className="grid gap-3 p-5 sm:grid-cols-2">
                {[
                  { label: "Version",     value: "1.0.0"       },
                  { label: "Environment", value: "Development" },
                  { label: "Node.js",     value: ">=18.0.0"    },
                  { label: "Framework",   value: "Next.js 16"  },
                ].map(({ label, value }) => (
                  <div key={label} className="rounded-lg bg-muted p-3">
                    <p className="text-xs text-muted-foreground">{label}</p>
                    <p className="mt-0.5 text-sm font-semibold text-foreground">{value}</p>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {tab === "Security" && (
            <div className="space-y-5">
              <Card>
                <div className="border-b border-border px-5 py-4">
                  <h2 className="text-sm font-semibold text-foreground">Change Password</h2>
                  <p className="text-xs text-muted-foreground mt-0.5">Update your chatbot access password</p>
                </div>
                <div className="p-5 space-y-4">
                  <label className="grid gap-1.5">
                    <span className="text-xs font-semibold text-foreground">Current Password</span>
                    <Input
                      type="password"
                      value={currentPassword}
                      onChange={(e) => setCurrentPassword(e.target.value)}
                      placeholder="Enter current password"
                    />
                  </label>
                  <label className="grid gap-1.5">
                    <span className="text-xs font-semibold text-foreground">New Password</span>
                    <Input
                      type="password"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      placeholder="Enter new password"
                    />
                  </label>
                  <label className="grid gap-1.5">
                    <span className="text-xs font-semibold text-foreground">Confirm Password</span>
                    <Input
                      type="password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="Confirm new password"
                    />
                  </label>
                  <div className="flex justify-end gap-2 pt-2">
                    <Button
                      variant="outline"
                      onClick={() => {
                        setCurrentPassword("");
                        setNewPassword("");
                        setConfirmPassword("");
                      }}
                    >
                      Cancel
                    </Button>
                    <Button onClick={handlePasswordUpdate} disabled={isUpdatingPassword}>
                      {isUpdatingPassword ? "Updating..." : "Update Password"}
                    </Button>
                  </div>
                </div>
              </Card>

              <Card>
                <div className="border-b border-border px-5 py-4">
                  <h2 className="text-sm font-semibold text-foreground">Security Settings</h2>
                </div>
                <div className="p-5 space-y-3">
                  {[
                    { label: "Enforce HTTPS",           defaultChecked: true  },
                    { label: "API Key Rotation Alerts",  defaultChecked: true  },
                    { label: "Two-Factor Authentication", defaultChecked: false },
                  ].map(({ label, defaultChecked }) => (
                    <label key={label} className="flex items-center justify-between rounded-lg border border-border p-3 cursor-pointer hover:bg-muted transition-colors">
                      <span className="text-sm font-medium text-foreground">{label}</span>
                      <input type="checkbox" defaultChecked={defaultChecked} className="h-4 w-4 accent-primary" />
                    </label>
                  ))}
                </div>
              </Card>
            </div>
          )}

          {(tab === "Appearance" || tab === "Notifications") && (
            <Card className="p-5">
              <p className="text-sm text-muted-foreground">
                {tab} settings will be available in an upcoming update.
              </p>
            </Card>
          )}

          {/* Danger zone */}
          <Card className="border-destructive/30">
            <div className="border-b border-destructive/20 px-5 py-4">
              <h2 className="text-sm font-semibold text-destructive">Danger Zone</h2>
              <p className="text-xs text-muted-foreground mt-0.5">Irreversible actions — proceed with caution</p>
            </div>
            <div className="flex flex-wrap gap-3 p-5">
              <Button variant="outline" onClick={() => setDanger("Clear cache")}>
                Clear Cache
              </Button>
              <Button variant="destructive" onClick={() => setDanger("Reset configuration")}>
                Reset Configuration
              </Button>
            </div>
          </Card>
        </div>
      </div>

      <Dialog open={Boolean(danger)} title={`Confirm: ${danger}`} onClose={() => setDanger("")}>
        <p className="text-sm text-muted-foreground">
          Are you sure you want to <strong>{danger?.toLowerCase()}</strong>? This action may not be reversible.
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" onClick={() => setDanger("")}>Cancel</Button>
          <Button variant="destructive" onClick={() => { toast.success(`${danger} completed`); setDanger(""); }}>
            Confirm
          </Button>
        </div>
      </Dialog>
    </WithLayout>
  );
}
