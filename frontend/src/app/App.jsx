import { Suspense } from "react";
import { RouterProvider } from "react-router-dom";

import { AppProviders } from "./providers.jsx";
import { router } from "./router.jsx";

// Route components are code-split, so the first render of a page may wait on its chunk.
function RouteFallback() {
  return (
    <div className="grid min-h-screen place-items-center bg-surface">
      <div className="text-sm text-muted">Loading...</div>
    </div>
  );
}

export default function App() {
  return (
    <AppProviders>
      <Suspense fallback={<RouteFallback />}>
        <RouterProvider router={router} />
      </Suspense>
    </AppProviders>
  );
}
