import WithLayout from "@/components/layout/with-layout";
import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <WithLayout>
      <div className="mb-6 flex items-center justify-between">
        <div><Skeleton className="h-8 w-48 mb-2" /><Skeleton className="h-4 w-56" /></div>
        <div className="flex gap-2"><Skeleton className="h-9 w-28" /><Skeleton className="h-9 w-24" /></div>
      </div>
      <Skeleton className="h-28 mb-4" />
      <Skeleton className="h-80" />
    </WithLayout>
  );
}
