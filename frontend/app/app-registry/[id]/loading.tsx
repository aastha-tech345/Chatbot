import WithLayout from "@/components/layout/with-layout";
import { Skeleton } from "@/components/ui/skeleton";
export default function Loading() { return <WithLayout><Skeleton className="h-20" /><Skeleton className="mt-5 h-96" /></WithLayout>; }
