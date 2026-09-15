import { Navigate, Outlet } from "react-router-dom";

import { useAuth } from "../../context/AuthContext.jsx";
import { useCustomer } from "../../context/CustomerContext.jsx";

export function BusinessProtectedRoute({ adminOnly = false }) {
  const { isAuthenticated, isPlatformAdmin, isCashier, isAuthReady } = useAuth();

  if (!isAuthReady) {
    return <section className="p-6 text-sm text-muted">Checking your session...</section>;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // A cashier shares the business login, so their token can reach these routes. Send
  // them to their own workspace instead. Every owner and admin API re-checks the account
  // type server-side, so this redirect is for clarity, not for security.
  if (isCashier) {
    return <Navigate to="/cashier" replace />;
  }

  if (adminOnly && !isPlatformAdmin) {
    return <Navigate to="/dashboard" replace />;
  }

  return <Outlet />;
}

export function CashierProtectedRoute() {
  const { isAuthenticated, isCashier, isAuthReady } = useAuth();

  if (!isAuthReady) {
    return <section className="p-6 text-sm text-muted">Checking your session...</section>;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (!isCashier) {
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
