"use client";
import { useRef } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import WithLayout from "@/components/layout/with-layout";
import { BackLink, PageHeader } from "@/components/common/page-header";
import { ApplicationForm } from "@/components/applications/application-form";
import { Skeleton } from "@/components/ui/skeleton";
import { getApplication, updateApplication } from "@/lib/api/applications";
import { ApplicationFormValues } from "@/lib/validations/application";
import { useAppRegistryId } from "../app-tabs";

export default function EditApplicationPage() {
  const serviceKey = useRef("");
  const id = useAppRegistryId();
  const router = useRouter();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["application", id], queryFn: () => getApplication(id) });
  const mutation = useMutation({
    mutationFn: async (values: ApplicationFormValues) => {
      const app = await updateApplication(id, { ...values, serviceKey: serviceKey.current });
      serviceKey.current = "";
      return app;
    },
    onError: () => toast.error("Unable to update application"),
    onSuccess: () => {
      qc.invalidateQueries();
      toast.success("Application updated successfully");
      router.push(`/app-registry/${id}`);
    },
  });

  return (
    <WithLayout>
      <BackLink />
      <PageHeader title="Edit Application" subtitle="Update your application configuration" />
      {isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-48" />
          <Skeleton className="h-48" />
        </div>
      ) : data ? (
        <ApplicationForm initial={data} submitLabel="Save Changes" onSubmit={({ serviceKey: secret, ...values }) => { serviceKey.current = secret || ""; mutation.mutate(values); }} />
      ) : null}
    </WithLayout>
  );
}
