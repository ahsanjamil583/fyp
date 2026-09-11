import {
  BarChart3,
  Bell,
  Bot,
  Boxes,
  CreditCard,
  FileText,
  Globe,
  MessageCircle,
  MessageSquare,
  Puzzle,
  ShoppingBag,
  Users,
} from "lucide-react";

/**
 * Module codes are machine names (`website_builder`, `ai_chat`). They were being printed
 * to the screen as-is, which reads like a database dump. This maps each one to a human
 * label, an icon and a tone so every surface presents modules the same way.
 */
const MODULE_META = {
  customers: { label: "Customers", icon: Users, tone: "blue" },
  items: { label: "Items & Catalog", icon: Boxes, tone: "violet" },
  website_builder: { label: "Website Builder", icon: Globe, tone: "purple" },
  customer_portal: { label: "Customer Portal", icon: ShoppingBag, tone: "green" },
  analytics: { label: "Analytics", icon: BarChart3, tone: "orange" },
  ai_chat: { label: "AI Chat", icon: MessageSquare, tone: "purple" },
  owner_agent: { label: "Owner AI Assistant", icon: Bot, tone: "violet" },
  whatsapp_agent: { label: "WhatsApp Agent", icon: MessageCircle, tone: "green" },
  payments: { label: "Payments", icon: CreditCard, tone: "blue" },
  reports: { label: "Reports", icon: FileText, tone: "orange" },
  notifications: { label: "Notifications", icon: Bell, tone: "red" },
};

/** Turns any unmapped code into something readable rather than showing the raw slug. */
export function humanizeModuleCode(code) {
  if (!code) return "";
  return MODULE_META[code]?.label || String(code).replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function moduleMeta(code) {
  return MODULE_META[code] || { label: humanizeModuleCode(code), icon: Puzzle, tone: "slate" };
}
