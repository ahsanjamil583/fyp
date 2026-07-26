import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useMemo } from "react";

import { AuthProvider } from "../context/AuthContext.jsx";
import { CustomerProvider } from "../context/CustomerContext.jsx";
import { ModuleProvider } from "../context/ModuleContext.jsx";
import { TenantProvider } from "../context/TenantContext.jsx";

export function AppProviders({ children }) {
  const queryClient = useMemo(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      }),
    [],
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <CustomerProvider>
          <TenantProvider>
            <ModuleProvider>{children}</ModuleProvider>
          </TenantProvider>
        </CustomerProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
