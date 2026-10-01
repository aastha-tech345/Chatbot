import { z } from "zod";

export const applicationSchema = z.object({
  serviceKey: z.string().optional(),
  authType: z.string().optional(),
  name: z.string().min(2, "Application name is required"),
  appId: z.string().regex(/^[a-z][a-z0-9_-]*$/, "Start with a lowercase letter. Use lowercase letters, numbers, hyphens, or underscores"),
  description: z.string().optional(),
  type: z.string().min(1, "Application type is required"),
  baseUrl: z.string().url("Enter a valid URL"),
  docsUrl: z.string().url("Enter a valid URL").optional().or(z.literal("")),
  status: z.enum(["Active", "Inactive", "Testing"]).optional()
});

export type ApplicationFormValues = z.infer<typeof applicationSchema>;
