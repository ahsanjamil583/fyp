import { Home, LogIn, Store, UserPlus, UserRound } from "lucide-react";
import { Shell } from "./Shell.jsx";

const navItems = [
  { to: "/", label: "Home", end: true, icon: Home },
  { to: "/login", label: "Business Login", icon: LogIn },
  { to: "/register", label: "Business Register", icon: UserPlus },
  { to: "/customer/login", label: "Customer Login", icon: Store },
  { to: "/customer/register", label: "Customer Register", icon: UserRound },
];

export function PublicLayout() {
  return <Shell title="Public Website" subtitle="Phase 1 foundation" navItems={navItems} />;
}
