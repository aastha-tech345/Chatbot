export function generateStaticParams() {
  return [{ id: "__static_export_placeholder__" }];
}

export default function AppRegistryIdLayout({ children }: { children: React.ReactNode }) {
  return children;
}
