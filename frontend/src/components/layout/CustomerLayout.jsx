import { Shell } from "./Shell.jsx";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useCustomer } from "../../context/CustomerContext.jsx";
import { logoutCustomer } from "../../services/customerAuthApi.js";

const navItems = [
  { to: "/customer/marketplace", label: "Marketplace" },
  { to: "/customer/cart", label: "Cart" },
  { to: "/customer/orders", label: "Orders" },
  { to: "/customer/profile", label: "Profile" },
  { to: "/customer/notifications", label: "Notifications" },
];

export function CustomerLayout() {
  const navigate = useNavigate();
  const { customer, clearCustomerSession } = useCustomer();
  const [sidebarPanel, setSidebarPanel] = useState(null);

  async function handleLogout() {
    try {
      await logoutCustomer();
    } catch {
      // Clear local auth state even if the backend logout request fails.
    }
    clearCustomerSession();
    navigate("/customer/login", { replace: true });
  }

  const asideFooter = (
    <div className="space-y-3">
      <div className="rounded-md bg-surface p-3 text-xs text-muted">
        <div className="font-semibold text-ink">{customer?.fullName || "Signed in"}</div>
        <div className="mt-1 break-all">{customer?.email}</div>
      </div>
      <button
        type="button"
        onClick={handleLogout}
        className="w-full rounded-md border border-line px-3 py-2 text-sm font-semibold text-ink transition hover:bg-surface"
      >
        Logout
      </button>
      {sidebarPanel ? <div className="pt-2">{sidebarPanel}</div> : null}
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

  return (
    <Shell
      title="Customer Portal"
      subtitle="Marketplace, cart, and orders"
      navItems={navItems}
      asideFooter={asideFooter}
      headerActions={headerActions}
      outletContext={{ setCustomerSidebarPanel: setSidebarPanel }}
    />
  );
}
