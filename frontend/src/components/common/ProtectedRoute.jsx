import { Navigate, Outlet } from "react-router-dom";

import { useAuth } from "../../context/AuthContext.jsx";
import { useCustomer } from "../../context/CustomerContext.jsx";

export function BusinessProtectedRoute({ adminOnly = false }) {
  const { isAuthenticated, isPlatformAdmin, isAuthReady } = useAuth();

  if (!isAuthReady) {
    return <section className="p-6 text-sm text-muted">Checking your session...</section>;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (adminOnly && !isPlatformAdmin) {
    return <Navigate to="/dashboard" replace />;
  }

  return <Outlet />;
}

export function CustomerProtectedRoute() {
  const { isCustomerAuthenticated } = useCustomer();

  if (!isCustomerAuthenticated) {
    return <Navigate to="/customer/login" replace />;
  }

  return <Outlet />;
}
