"use client";
import WithLayout from "@/components/layout/with-layout";
import { EmptyState } from "@/components/common/empty-error";
import { Button } from "@/components/ui/button";

export default function Error({ reset }: { reset: () => void }) {
  return (
    <WithLayout>
      <EmptyState
        variant="error-state"
        title="Failed to load application"
        description="Could not fetch this application's data."
        action={<Button onClick={reset}>Retry</Button>}
      />
    </WithLayout>
  );
}
