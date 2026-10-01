"use client";
import WithLayout from "@/components/layout/with-layout";
import { EmptyState } from "@/components/common/empty-error";
import { Button } from "@/components/ui/button";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <WithLayout>
      <EmptyState
        variant="error-state"
        title="Something went wrong"
        description={error?.message || "Failed to load this page. Please try again."}
        action={<Button onClick={reset}>Try again</Button>}
      />
    </WithLayout>
  );
}
