import { Shell } from "./Shell.jsx";

const navItems = [
  { to: "/", label: "Home", end: true },
  { to: "/login", label: "Business Login" },
  { to: "/register", label: "Business Register" },
  { to: "/customer/login", label: "Customer Login" },
  { to: "/customer/register", label: "Customer Register" },
];

export function PublicLayout() {
  return <Shell title="Public Website" subtitle="Phase 1 foundation" navItems={navItems} />;
}
