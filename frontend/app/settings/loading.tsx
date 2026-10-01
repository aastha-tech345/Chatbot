import WithLayout from "@/components/layout/with-layout";
import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <WithLayout>
      <div className="mb-6"><Skeleton className="h-8 w-32 mb-2" /><Skeleton className="h-4 w-56" /></div>
      <div className="grid gap-5 lg:grid-cols-[200px_1fr]">
        <Skeleton className="h-56" />
        <Skeleton className="h-96" />
      </div>
    </WithLayout>
  );
}
