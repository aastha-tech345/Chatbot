import { Badge } from "@/components/ui/badge";
import { AppStatus, LogLevel, RouteStatus } from "@/types";

type StatusValue = AppStatus | RouteStatus | LogLevel | string;

function getVariant(status: StatusValue): "success" | "destructive" | "warning" | "info" | "secondary" {
  switch (status) {
    case "Active":
    case "Available":
    case "SUCCESS":
      return "success";
    case "Inactive":
    case "ERROR":
    case "Error":
      return "destructive";
    case "WARNING":
    case "Testing":
    case "Disabled":
      return "warning";
    case "INFO":
      return "info";
    default:
      return "secondary";
  }
}

export function StatusBadge({ status }: { status: StatusValue }) {
  return <Badge variant={getVariant(status)}>{status}</Badge>;
}
