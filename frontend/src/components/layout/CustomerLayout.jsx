import { Bell, Bot, LogOut, Receipt, ShoppingBag, ShoppingCart, Store, UserRound } from "lucide-react";
import { Shell } from "./Shell.jsx";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useCustomer } from "../../context/CustomerContext.jsx";
import { logoutCustomer } from "../../services/customerAuthApi.js";

const navItems = [
  { to: "/customer/marketplace", label: "Browse Businesses", icon: Store, section: "Shop" },
  { to: "/customer/cart", label: "Cart & Checkout", icon: ShoppingCart, section: "Shop" },
  { to: "/customer/orders", label: "Orders & Payments", icon: Receipt, section: "Track" },
  { to: "/customer/notifications", label: "Notifications", icon: Bell, section: "Track" },
  { to: "/customer/profile", label: "Profile Settings", icon: UserRound, section: "Account" },
];

const navSections = [
  { title: "Shop", items: navItems.filter((item) => item.section === "Shop") },
  { title: "Track", items: navItems.filter((item) => item.section === "Track") },
  { title: "Account", collapsedByDefault: true, items: navItems.filter((item) => item.section === "Account") },
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
    <div className="space-y-2">
      <div className="flex items-center gap-3 rounded-rail bg-sidebar-card px-3 py-2.5">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-sidebar-active text-sm font-bold text-white">
          {(customer?.fullName || "C").charAt(0).toUpperCase()}
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-white">{customer?.fullName || "Signed in"}</div>
          <div className="truncate text-[11px] text-sidebar-muted">{customer?.email}</div>
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
      {sidebarPanel ? <div className="pt-2">{sidebarPanel}</div> : null}
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
      title="Customer Portal"
      subtitle="Marketplace, cart, and orders"
      navItems={navItems}
      navSections={navSections}
      asideFooter={asideFooter}
      headerActions={headerActions}
      flowSteps={[
        { label: "Browse", icon: Store },
        { label: "Choose", icon: ShoppingBag },
        { label: "Ask AI", icon: Bot },
        { label: "Checkout", icon: ShoppingCart },
        { label: "Track", icon: Receipt },
      ]}
      outletContext={{ setCustomerSidebarPanel: setSidebarPanel }}
    />
  );
}
