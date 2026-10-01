"use client";
import WithLayout from "@/components/layout/with-layout";
import { EmptyState } from "@/components/common/empty-error";
import { Button } from "@/components/ui/button";

export default function Error({ reset }: { reset: () => void }) {
  return (
    <WithLayout>
      <EmptyState
        variant="error-state"
        title="Failed to load App Registry"
        description="Could not fetch applications. Please check your connection and try again."
        action={<Button onClick={reset}>Retry</Button>}
      />
    </WithLayout>
  );
}
