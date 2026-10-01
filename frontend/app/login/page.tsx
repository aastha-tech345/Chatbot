"use client";
import { useEffect, useState, lazy, Suspense } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Bot, Eye, EyeOff, Loader2, Shield } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { login } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { IllustrationLoginBranding } from "@/components/ui/illustrations";

// Three.js canvas — lazy loaded, client only
const NeuralCanvas = lazy(() =>
  import("@/components/ui/neural-canvas").then((m) => ({ default: m.NeuralCanvas }))
);

const schema = z.object({
  email:    z.string().min(1, "Email is required"),
  password: z.string().min(1, "Password is required"),
  remember: z.boolean().optional(),
});
type FormValues = z.infer<typeof schema>;

export default function LoginPage() {
  const { user, ready, setUser } = useAuth();
  const router = useRouter();
  const [showPass, setShowPass]     = useState(false);
  const [serverError, setServerError] = useState("");

  useEffect(() => {
    if (ready && user) router.replace("/dashboard");
  }, [ready, user, router]);

  const { register, handleSubmit, formState: { errors, isSubmitting } } =
    useForm<FormValues>({ resolver: zodResolver(schema) });

  async function onSubmit(values: FormValues) {
    setServerError("");
    try {
      const authUser = await login({ email: values.email, password: values.password });
      setUser(authUser);
      router.replace("/dashboard");
    } catch (err: unknown) {
      setServerError(err instanceof Error ? err.message : "Unable to connect. Please try again.");
    }
  }

  if (!ready || user) return null;

  return (
    <div className="flex min-h-screen bg-background">

      {/* ── Left panel — branding + Three.js canvas ── */}
      <div className="relative hidden lg:flex lg:w-[52%] flex-col items-center justify-center overflow-hidden bg-[hsl(252_84%_57%)]">
        {/* Neural network background */}
        <Suspense fallback={null}>
          <NeuralCanvas className="absolute inset-0 h-full w-full opacity-60" />
        </Suspense>

        {/* Overlay gradient for readability */}
        <div className="absolute inset-0 bg-gradient-to-br from-[hsl(252_84%_42%/0.5)] to-transparent pointer-events-none" />

        {/* Branding content */}
        <div className="relative z-10 flex flex-col items-center text-center px-10">
          <IllustrationLoginBranding className="h-56 w-56 mb-8 opacity-90" />
          <h1 className="text-3xl font-bold text-white">Master Chatbot</h1>
          <p className="mt-2 text-base text-white/75 max-w-xs leading-relaxed">
            Multi-Application AI Assistant for your enterprise workflows
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            {["AI-Powered","Multi-App","Real-time","Secure"].map((tag) => (
              <span key={tag}
                className="rounded-full border border-white/25 bg-white/10 px-3 py-1 text-xs font-medium text-white/80">
                {tag}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* ── Right panel — login form ── */}
      <div className="flex flex-1 flex-col items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm page-fade">

          {/* Mobile logo (hidden on desktop since left panel has it) */}
          <div className="mb-8 flex flex-col items-center text-center lg:hidden">
            <div className="mb-3 grid h-12 w-12 place-items-center rounded-xl bg-primary">
              <Bot className="h-6 w-6 text-white" />
            </div>
            <h1 className="text-xl font-bold text-foreground">Master Chatbot</h1>
            <p className="mt-1 text-sm text-muted-foreground">Multi-Application AI Assistant</p>
          </div>

          {/* Desktop heading */}
          <div className="mb-6 hidden lg:block">
            <p className="text-2xs font-semibold uppercase tracking-widest text-primary mb-1">
              Admin Panel
            </p>
            <h2 className="text-2xl font-bold text-foreground">Welcome back</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Sign in to access the Master Chatbot dashboard
            </p>
          </div>

          {/* Form card */}
          <div className="rounded-xl border border-border bg-card p-6 shadow-md">
            <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">

              {/* Email */}
              <div className="space-y-1.5">
                <label htmlFor="email" className="text-xs font-semibold text-foreground">
                  Email / Username
                </label>
                <Input
                  id="email"
                  type="email"
                  placeholder="admin@example.com"
                  autoComplete="email"
                  autoFocus
                  {...register("email")}
                  aria-invalid={!!errors.email}
                />
                {errors.email && (
                  <p className="text-xs text-destructive">{errors.email.message}</p>
                )}
              </div>

              {/* Password */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label htmlFor="password" className="text-xs font-semibold text-foreground">
                    Password
                  </label>
                  <button type="button"
                    className="text-xs text-primary hover:underline underline-offset-2 transition-colors">
                    Forgot password?
                  </button>
                </div>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPass ? "text" : "password"}
                    placeholder="••••••••"
                    autoComplete="current-password"
                    className="pr-9"
                    {...register("password")}
                    aria-invalid={!!errors.password}
                  />
                  <button type="button" tabIndex={-1}
                    onClick={() => setShowPass(!showPass)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                    aria-label="Toggle password visibility">
                    {showPass ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                  </button>
                </div>
                {errors.password && (
                  <p className="text-xs text-destructive">{errors.password.message}</p>
                )}
              </div>

              {/* Remember me */}
              <label className="flex cursor-pointer items-center gap-2">
                <input type="checkbox" className="h-4 w-4 rounded accent-primary"
                  {...register("remember")} />
                <span className="text-xs text-muted-foreground">Remember me</span>
              </label>

              {/* Server error */}
              {serverError && (
                <div className="rounded-md border border-destructive/30 bg-[hsl(var(--destructive-bg))] px-3 py-2.5">
                  <p className="text-xs text-destructive">{serverError}</p>
                </div>
              )}

              {/* Submit */}
              <Button type="submit" className="w-full" size="lg" disabled={isSubmitting}>
                {isSubmitting ? (
                  <><Loader2 className="h-4 w-4 animate-spin" /> Logging in...</>
                ) : "Login"}
              </Button>
            </form>
          </div>

          {/* Footer note */}
          <div className="mt-5 flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
            <Shield className="h-3 w-3" />
            Authorized access only · Admin panel
          </div>
        </div>
      </div>
    </div>
  );
}
