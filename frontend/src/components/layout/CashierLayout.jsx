import { LayoutDashboard, LogOut, PlusCircle, Receipt, ShoppingCart, Store } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { BrandLogo } from "../common/BrandLogo.jsx";
import { useAuth } from "../../context/AuthContext.jsx";
import { logoutBusiness } from "../../services/authApi.js";
import { getCashierProfile } from "../../services/cashierApi.js";

/**
 * A till, not a dashboard.
 *
 * The owner shell has thirty navigation entries, a business switcher and a plan badge.
 * None of that belongs on a screen someone uses forty times an hour with a queue in
 * front of them, so this layout is four destinations, large tap targets, and nothing
 * that can be clicked by mistake. It also prints cleanly: everything outside the page
 * body is hidden by the `print-hide` class when a receipt goes to the printer.
 */

const navItems = [
  { to: "/cashier", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/cashier/orders/new", label: "New Order", icon: PlusCircle },
  { to: "/cashier/orders", label: "Orders", icon: ShoppingCart },
  { to: "/cashier/receipts", label: "Receipts", icon: Receipt },
];

function navClass({ isActive }) {
  return [
    "flex flex-1 items-center justify-center gap-2 rounded-rail px-3 py-3 text-sm font-bold transition sm:flex-none sm:justify-start sm:px-4",
    isActive ? "bg-sidebar-active text-white shadow-nav-active" : "text-sidebar-text hover:bg-sidebar-hover hover:text-white",
  ].join(" ");
}

export function CashierLayout() {
  const navigate = useNavigate();
  const { user, clearSession } = useAuth();
  const [profile, setProfile] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getCashierProfile()
      .then((data) => {
        if (!cancelled) setProfile(data);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleLogout() {
    try {
      await logoutBusiness();
    } catch {
      // Clear the local session even if the sign-out request fails.
    }
    clearSession();
    navigate("/login", { replace: true });
  }

  const businessName = profile?.business?.name || "";
  const cashierName = profile?.fullName || user?.fullName || "Cashier";

  return (
    <div className="min-h-screen bg-page">
      <header className="print-hide sticky top-0 z-30 bg-sidebar-rail shadow-rail">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 px-4 py-3 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <BrandLogo tone="dark" showWordmark={false} imageClassName="h-9 w-9" />
            <div className="min-w-0">
              <div className="truncate text-sm font-extrabold leading-tight text-white">{businessName || "Cashier Counter"}</div>
              <div className="flex items-center gap-1.5 truncate text-[11px] font-medium text-sidebar-muted">
                <Store size={12} />
                {cashierName}
                {profile?.employeeCode ? ` · ${profile.employeeCode}` : ""}
              </div>
            </div>
          </div>

          <div className="ml-auto flex items-center gap-2">
            <span className="hidden rounded-full bg-sidebar-card px-3 py-1.5 text-[11px] font-bold text-white sm:inline-flex">Cashier</span>
            <button
              type="button"
              onClick={handleLogout}
              className="inline-flex items-center gap-2 rounded-rail border border-white/10 px-3 py-2.5 text-sm font-bold text-sidebar-text transition hover:bg-sidebar-hover hover:text-white"
            >
              <LogOut size={16} />
              <span className="hidden sm:inline">Logout</span>
            </button>
          </div>

          <nav className="flex w-full items-stretch gap-2 overflow-x-auto pb-1 sm:w-auto sm:pb-0">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink key={item.to} to={item.to} end={item.end} className={navClass}>
                  <Icon size={18} className="shrink-0" strokeWidth={2.2} />
                  <span className="whitespace-nowrap">{item.label}</span>
                </NavLink>
              );
            })}
          </nav>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6">
        <Outlet />
      </main>

      <footer className="print-hide border-t border-line bg-white px-4 py-4 text-center text-xs text-muted sm:px-6">
        BizXusAI Cashier Counter · {businessName}
      </footer>
    </div>
  );
}
