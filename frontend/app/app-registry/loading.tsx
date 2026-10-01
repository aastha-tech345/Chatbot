import WithLayout from "@/components/layout/with-layout";
import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <WithLayout>
      <div className="mb-6 flex items-center justify-between">
        <div><Skeleton className="h-8 w-40 mb-2" /><Skeleton className="h-4 w-56" /></div>
        <Skeleton className="h-9 w-36" />
      </div>
      <div className="mb-5 grid gap-4 sm:grid-cols-4">
        {[1,2,3,4].map((i) => <Skeleton key={i} className="h-28" />)}
      </div>
      <Skeleton className="h-96" />
    </WithLayout>
  );
}
