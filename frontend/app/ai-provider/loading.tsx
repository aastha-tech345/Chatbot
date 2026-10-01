import WithLayout from "@/components/layout/with-layout";
import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <WithLayout>
      <div className="mb-6"><Skeleton className="h-8 w-40 mb-2" /><Skeleton className="h-4 w-60" /></div>
      <div className="grid gap-5 lg:grid-cols-[1fr_380px]">
        <div className="space-y-4">
          <Skeleton className="h-28" />
          <div className="grid gap-3 sm:grid-cols-2">
            {[1,2,3,4].map((i) => <Skeleton key={i} className="h-36" />)}
          </div>
        </div>
        <Skeleton className="h-96" />
      </div>
    </WithLayout>
  );
}
