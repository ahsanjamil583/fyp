import { Boxes, CreditCard, FileText, LayoutDashboard, LogOut, SquareStack, Tags, Users } from "lucide-react";
import { Shell } from "./Shell.jsx";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../../context/AuthContext.jsx";
import { logoutBusiness } from "../../services/authApi.js";

const navItems = [
  { to: "/admin", label: "Overview", end: true, icon: LayoutDashboard },
  { to: "/admin/users", label: "Users", icon: Users },
  { to: "/admin/tenants", label: "Tenants", icon: Boxes },
  { to: "/admin/business-categories", label: "Categories", icon: Tags },
  { to: "/admin/modules", label: "Modules", icon: SquareStack },
  { to: "/admin/payments", label: "Payments", icon: CreditCard },
  { to: "/admin/reports", label: "Reports", icon: FileText },
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
    <div className="space-y-2">
      <div className="flex items-center gap-3 rounded-rail bg-sidebar-card px-3 py-2.5">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-sidebar-active text-sm font-bold text-white">
          {(user?.fullName || "A").charAt(0).toUpperCase()}
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-white">{user?.fullName || "Signed in"}</div>
          <div className="truncate text-[11px] text-sidebar-muted">{user?.email}</div>
        </div>
      </div>
      <button
        type="button"
        onClick={handleLogout}
        className="flex w-full items-center gap-3 rounded-rail px-3.5 py-2.5 text-sm font-semibold text-sidebar-text transition hover:bg-sidebar-hover hover:text-white"
      >
        <LogOut size={18} className="shrink-0" />
        Logout
      </button>
    </div>
  );

  const headerActions = (
    <button
      type="button"
      onClick={handleLogout}
      className="ui-btn-secondary !rounded-full !py-2"
    >
      Logout
    </button>
  );

  return <Shell title="Admin Panel" subtitle="Platform controls" navItems={navItems} asideFooter={asideFooter} headerActions={headerActions} />;
}
