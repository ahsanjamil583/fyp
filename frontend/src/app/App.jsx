import { Suspense, useEffect } from "react";
import { RouterProvider } from "react-router-dom";

import { AppProviders } from "./providers.jsx";
import { router } from "./router.jsx";
import { setApiNavigationHandler } from "../services/apiClient.js";

// Route components are code-split, so the first render of a page may wait on its chunk.
function RouteFallback() {
  return (
    <div className="grid min-h-screen place-items-center bg-surface">
      <div className="text-sm text-muted">Loading...</div>
    </div>
  );
}

export default function App() {
  // Let the API layer navigate through the router instead of reloading the document.
  useEffect(() => {
    setApiNavigationHandler((to) => router.navigate(to, { replace: true }));
    return () => setApiNavigationHandler(null);
  }, []);

  return (
    <AppProviders>
      <Suspense fallback={<RouteFallback />}>
        <RouterProvider router={router} />
      </Suspense>
    </AppProviders>
  );
}
