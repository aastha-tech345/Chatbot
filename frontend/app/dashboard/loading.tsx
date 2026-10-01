import WithLayout from "@/components/layout/with-layout";
import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <WithLayout>
      <div className="mb-6">
        <Skeleton className="h-8 w-48 mb-2" />
        <Skeleton className="h-4 w-64" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[1,2,3,4].map((i) => <Skeleton key={i} className="h-28" />)}
      </div>
      <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_320px]">
        <Skeleton className="h-64" />
        <div className="space-y-5">
          <Skeleton className="h-48" />
          <Skeleton className="h-48" />
        </div>
      </div>
    </WithLayout>
  );
}
