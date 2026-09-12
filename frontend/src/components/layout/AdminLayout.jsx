import { Boxes, ClipboardCheck, CreditCard, FileText, LayoutDashboard, LogOut, ShieldCheck, SquareStack, Tags, Users } from "lucide-react";
import { Shell } from "./Shell.jsx";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../../context/AuthContext.jsx";
import { logoutBusiness } from "../../services/authApi.js";

const navItems = [
  { to: "/admin", label: "Platform Overview", end: true, icon: LayoutDashboard, section: "Operations" },
  { to: "/admin/tenants", label: "Business Review", icon: Boxes, section: "Review Queue" },
  { to: "/admin/users", label: "Users & Roles", icon: Users, section: "Review Queue" },
  { to: "/admin/payments", label: "Payments", icon: CreditCard, section: "Monitoring" },
  { to: "/admin/reports", label: "Reports", icon: FileText, section: "Monitoring" },
  { to: "/admin/business-categories", label: "Categories", icon: Tags, section: "Configuration" },
  { to: "/admin/modules", label: "Modules", icon: SquareStack, section: "Configuration" },
];

const navSections = [
  { title: "Operations", items: navItems.filter((item) => item.section === "Operations") },
  { title: "Review Queue", items: navItems.filter((item) => item.section === "Review Queue") },
  { title: "Monitoring", items: navItems.filter((item) => item.section === "Monitoring") },
  { title: "Configuration", collapsedByDefault: true, items: navItems.filter((item) => item.section === "Configuration") },
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

  return (
    <Shell
      title="Admin Panel"
      subtitle="Review, approvals, users, payments, and platform health"
      navItems={navItems}
      navSections={navSections}
      asideFooter={asideFooter}
      headerActions={headerActions}
      flowSteps={[
        { label: "Review", icon: ClipboardCheck },
        { label: "Preview", icon: Boxes },
        { label: "Approve", icon: ShieldCheck },
        { label: "Monitor", icon: CreditCard },
        { label: "Report", icon: FileText },
      ]}
    />
  );
}
