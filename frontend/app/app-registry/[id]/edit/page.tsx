import EditApplicationPage from "./client-page";

export function generateStaticParams() {
  return [{ id: "__static_export_placeholder__" }];
}

export default function Page() {
  return <EditApplicationPage />;
}
