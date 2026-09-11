import {
  Activity,
  AlertTriangle,
  Building2,
  BadgeCheck,
  Banknote,
  Bell,
  CalendarCheck,
  BarChart3,
  Bot,
  Boxes,
  BookOpen,
  CheckCircle2,
  ClipboardList,
  CreditCard,
  FileText,
  Globe,
  HelpCircle,
  Inbox,
  LayoutGrid,
  LayoutTemplate,
  MessageSquare,
  Package,
  Receipt,
  Send,
  Settings2,
  Sparkles,
  SquareStack,
  StickyNote,
  Tags,
  Clock,
  Contact,
  Database,
  Languages,
  ListChecks,
  MapPin,
  PlayCircle,
  RotateCcw,
  ShoppingCart,
  SlidersHorizontal,
  Terminal,
  TrendingUp,
  Upload,
  Users,
  Webhook,
  Wrench,
} from "lucide-react";

/**
 * Card section headings, with an icon chosen from the heading text.
 *
 * Every page was writing its own bare <h2>, which is why cards had no visual anchor. The
 * mapping lives here rather than at 50-odd call sites so the same idea ("Payments",
 * "Knowledge") always gets the same mark, and a new heading still renders sensibly.
 * Order matters: the first matching keyword wins, so specific terms precede general ones.
 */
const ICON_RULES = [
  // --- metric labels (checked first: they are more specific) ---
  [/alert|unread|overdue|failed/i, AlertTriangle, "orange"],
  [/revenue|gross|earning|amount|total paid/i, Banknote, "green"],
  [/avg|average|value|rate|conversion|growth/i, TrendingUp, "violet"],
  [/booking/i, CalendarCheck, "orange"],
  [/quote/i, ClipboardList, "blue"],
  [/notification|reminder/i, Bell, "orange"],
  [/verified|active|enabled|ready|complete/i, BadgeCheck, "green"],
  [/order|purchase/i, ShoppingCart, "purple"],
  [/refund|returned/i, RotateCcw, "orange"],
  [/received|net |paid count|cod/i, Banknote, "green"],
  [/pending|awaiting|review/i, Clock, "orange"],
  [/checklist|sign-off|readiness|verification|submit these/i, ListChecks, "green"],
  [/command|runtime|terminal|script/i, Terminal, "slate"],
  [/demo/i, PlayCircle, "purple"],
  [/business name|business identity|slug|brand/i, Building2, "violet"],
  [/location|address/i, MapPin, "blue"],
  [/contact|phone|email/i, Contact, "blue"],
  [/language/i, Languages, "purple"],
  [/inquir/i, MessageSquare, "purple"],
  [/preset|preference|option/i, SlidersHorizontal, "slate"],
  [/record|entry|log/i, Database, "slate"],
  [/status|state|health/i, Activity, "green"],
  [/total|sum|count/i, BarChart3, "violet"],

  // --- section headings ---
  [/webhook/i, Webhook, "purple"],
  [/stripe|payment|proof|invoice|billing/i, CreditCard, "blue"],
  [/transaction|outstanding|order/i, Receipt, "violet"],
  [/knowledge|rag|indexed|source/i, BookOpen, "purple"],
  [/faq|question/i, HelpCircle, "blue"],
  [/tool|trace/i, Wrench, "slate"],
  [/agent|assistant|bot/i, Bot, "violet"],
  [/chat|message|conversation|reply/i, MessageSquare, "purple"],
  [/hero|template|section|testimonial|preview/i, LayoutTemplate, "violet"],
  [/website|seo|domain/i, Globe, "blue"],
  [/module|plan|package|upgrade/i, SquareStack, "purple"],
  [/stock|catalog|item|product/i, Boxes, "violet"],
  [/categor/i, Tags, "orange"],
  [/user|role|tenant|customer|member/i, Users, "blue"],
  [/upload|import|file/i, Upload, "green"],
  [/approval|approved|confirm/i, CheckCircle2, "green"],
  [/request|inbox|submission/i, Inbox, "orange"],
  [/setting|connection|rule|config/i, Settings2, "slate"],
  [/recommend|prompt|ai |^ai$|summary/i, Sparkles, "purple"],
  [/form|field/i, ClipboardList, "blue"],
  [/note|log|history/i, StickyNote, "slate"],
  [/send|test/i, Send, "green"],
  [/report|mix|top |snapshot|analytic/i, BarChart3, "orange"],
  [/document|text|content/i, FileText, "slate"],
  [/deliver|shipment/i, Package, "green"],
];

const TONES = {
  violet: "bg-brand-100 text-brand",
  purple: "bg-purple-100 text-purple-600",
  blue: "bg-blue-50 text-blue-500",
  green: "bg-green-50 text-green-600",
  orange: "bg-orange-100 text-orange-600",
  slate: "bg-surface text-muted",
};

export function iconForHeading(text) {
  const label = String(text || "");
  const rule = ICON_RULES.find(([pattern]) => pattern.test(label));
  return { icon: rule?.[1] || LayoutGrid, tone: rule?.[2] || "violet" };
}

export function SectionTitle({ children, icon, tone, className = "" }) {
  const derived = iconForHeading(typeof children === "string" ? children : "");
  const Icon = icon || derived.icon;
  const toneClass = TONES[tone || derived.tone] || TONES.violet;

  return (
    <h2 className={`flex items-center gap-2.5 text-base font-bold text-ink ${className}`.trim()}>
      <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg ${toneClass}`}>
        <Icon size={16} strokeWidth={2.2} />
      </span>
      {children}
    </h2>
  );
}
