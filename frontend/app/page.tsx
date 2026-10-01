import { redirect } from "next/navigation";

// The AppLayout/WithLayout handles auth checks client-side.
// Root always redirects to dashboard; the RequireAuth wrapper sends
// unauthenticated users to /login from there.
export default function Home() {
  redirect("/dashboard");
}
