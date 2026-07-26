import { Shell } from "./Shell.jsx";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../../context/AuthContext.jsx";
import { logoutBusiness } from "../../services/authApi.js";

const navItems = [
  { to: "/admin", label: "Overview", end: true },
  { to: "/admin/users", label: "Users" },
  { to: "/admin/tenants", label: "Tenants" },
  { to: "/admin/business-categories", label: "Categories" },
  { to: "/admin/modules", label: "Modules" },
  { to: "/admin/payments", label: "Payments" },
  { to: "/admin/reports", label: "Reports" },
];

export function AdminLayout() {
  const navigate = useNavigate();
  const { clearSession, refreshSession, user } = useAuth();

  useEffect(() => {
    refreshSession().catch(() => {});

    function handleFocus() {
      refreshSession().catch(() => {});
    }

    window.addEventListener("focus", handleFocus);
    return () => {
      window.removeEventListener("focus", handleFocus);
    };
  }, [refreshSession]);

  async function handleLogout() {
    try {
      await logoutBusiness();
    } catch {
      // Clear local auth state even if the backend logout request fails.
    }
    clearSession();
    navigate("/login", { replace: true });
  }

  const asideFooter = (
    <div className="space-y-3">
      <div className="rounded-md bg-surface p-3 text-xs text-muted">
        <div className="font-semibold text-ink">{user?.fullName || "Admin"}</div>
        <div className="mt-1 break-all">{user?.email}</div>
      </div>
      <button
        type="button"
        onClick={handleLogout}
        className="w-full rounded-md border border-line px-3 py-2 text-sm font-semibold text-ink transition hover:bg-surface"
      >
        Logout
      </button>
    </div>
  );

  const headerActions = (
    <button
      type="button"
      onClick={handleLogout}
      className="rounded-md border border-line px-3 py-2 text-sm font-semibold text-ink transition hover:bg-surface"
    >
      Logout
    </button>
  );

  return <Shell title="Admin Panel" subtitle="Platform controls" navItems={navItems} asideFooter={asideFooter} headerActions={headerActions} />;
}
