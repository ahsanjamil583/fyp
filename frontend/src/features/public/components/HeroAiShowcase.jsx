import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Bot,
  CheckCircle2,
  Lock,
  MessageCircle,
  Package,
  RotateCcw,
  Zap,
} from "lucide-react";

/**
 * Animated AI Product Visualization & Live Simulation.
 * Demonstrates AI conversational catalog understanding, instant order processing,
 * and live revenue/inventory statistics synchronization.
 */
export function HeroAiShowcase() {
  const [step, setStep] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const isInitialStep = step === 0;

  useEffect(() => {
    if (isPaused) return;

    // Simulation sequence timings
    const timers = [
      setTimeout(() => setStep(1), 800), // Customer message shown
      setTimeout(() => setStep(2), 2000), // AI typing
      setTimeout(() => setStep(3), 3200), // AI replies
      setTimeout(() => setStep(4), 4600), // Catalog card pops up
      setTimeout(() => setStep(5), 5800), // Order created & metrics update
      setTimeout(() => {
        // Reset loop after a pause
        setStep(0);
      }, 10000),
    ];

    return () => timers.forEach(clearTimeout);
  }, [isInitialStep, isPaused]);

  const restartSimulation = () => {
    setStep(0);
  };

  const isOrderPlaced = step >= 5;

  return (
    <div
      className="relative mx-auto w-full max-w-xl lg:max-w-none"
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => setIsPaused(false)}
    >
      {/* Background ambient radial aura behind dashboard */}
      <div className="ai-glow-animate pointer-events-none absolute -inset-4 rounded-3xl bg-gradient-to-tr from-blue-200/60 via-sky-100/80 to-white blur-2xl" />

      {/* Main Glass Dashboard Shell */}
      <motion.div
        initial={{ opacity: 0, x: 40, scale: 0.96 }}
        animate={{ opacity: 1, x: 0, scale: 1 }}
        transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        className="relative overflow-hidden rounded-[1.7rem] border border-blue-100 bg-white/92 p-5 shadow-2xl shadow-blue-950/10 backdrop-blur-2xl md:p-6"
      >
        {/* Subtle interior lighting sheen */}
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-blue-300/70 to-transparent" />

        {/* Browser Top Navigation Rail */}
        <div className="flex items-center justify-between border-b border-blue-100 pb-3.5">
          <div className="flex items-center gap-2">
            <span className="h-3 w-3 rounded-full bg-rose-500/80" />
            <span className="h-3 w-3 rounded-full bg-amber-500/80" />
            <span className="h-3 w-3 rounded-full bg-emerald-500/80" />
            <div className="ml-2 flex items-center gap-1.5 rounded-lg border border-blue-100 bg-blue-50/70 px-2.5 py-1 text-[11px] font-medium text-slate-600">
              <Lock size={11} className="text-sky-300" />
              <span className="truncate">bizxus.ai/your-shop</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-blue-100 bg-blue-50 px-2.5 py-0.5 text-[10px] font-semibold text-blue-700">
              <span className="h-1.5 w-1.5 animate-ping rounded-full bg-sky-300" />
              AI Assistant: Active
            </span>
            <button
              type="button"
              onClick={restartSimulation}
              title="Replay interactive simulation"
              className="grid h-6 w-6 place-items-center rounded-md border border-blue-100 bg-white text-slate-500 transition hover:bg-blue-50 hover:text-blue-700"
            >
              <RotateCcw size={12} />
            </button>
          </div>
        </div>

        {/* Live Conversation Stream */}
        <div className="min-h-[170px] space-y-3.5 pt-4">
          {/* Customer Message */}
          <AnimatePresence>
            {step >= 1 && (
              <motion.div
                initial={{ opacity: 0, y: 10, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.35 }}
                className="flex items-start gap-2.5"
              >
                <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-sky-50 text-sky-600 ring-1 ring-sky-100">
                  <MessageCircle size={15} />
                </div>
                <div className="rounded-2xl rounded-tl-sm border border-blue-100 bg-slate-50 px-4 py-2.5 text-sm text-slate-800 shadow-sm backdrop-blur-md">
                  <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wider text-blue-600">
                    Customer on WhatsApp
                  </div>
                  <p className="leading-snug">Grey tracksuit ka price kya hai? Available hai?</p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* AI Typing Indicator */}
          <AnimatePresence>
            {step === 2 && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ duration: 0.2 }}
                className="flex items-center justify-end gap-2"
              >
                <div className="inline-flex items-center gap-1.5 rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-sky-400 [animation-delay:-0.3s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-sky-400 [animation-delay:-0.15s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-sky-400" />
                  <span className="ml-1 text-[11px] font-medium text-blue-700">AI checking live stock...</span>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* AI Message */}
          <AnimatePresence>
            {step >= 3 && (
              <motion.div
                initial={{ opacity: 0, y: 12, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.4 }}
                className="flex items-start justify-end gap-2.5"
              >
                <div className="max-w-[85%] rounded-2xl rounded-tr-sm border border-blue-500/20 bg-gradient-to-r from-blue-600 to-blue-700 px-4 py-2.5 text-sm font-medium text-white shadow-lg shadow-blue-600/20">
                  <div className="mb-0.5 flex items-center justify-between gap-2 text-[10px] font-bold uppercase tracking-wider text-sky-200">
                    <span>BizXus AI Assistant</span>
                    <span className="text-white/60">Instant Reply</span>
                  </div>
                  <p className="leading-snug">
                    Grey Tracksuit is PKR 4,800 and in stock. Want me to place the order?
                  </p>
                </div>
                <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-gradient-to-tr from-blue-600 to-sky-400 text-white shadow-md">
                  <Bot size={16} />
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Catalog & Order Recognition Pill */}
          <AnimatePresence>
            {step >= 4 && (
              <motion.div
                initial={{ opacity: 0, height: 0, y: 8 }}
                animate={{ opacity: 1, height: "auto", y: 0 }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.4 }}
                className="overflow-hidden"
              >
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-blue-100 bg-blue-50/80 px-3.5 py-2 text-xs text-blue-800">
                  <div className="flex items-center gap-2">
                    <span className="grid h-6 w-6 place-items-center rounded-lg bg-white text-blue-600 shadow-sm">
                      <Package size={13} />
                    </span>
                    <span className="font-semibold text-slate-950">Grey Tracksuit</span>
                    <span className="text-blue-600">PKR 4,800</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="rounded bg-white px-2 py-0.5 text-[10px] font-bold text-blue-700 shadow-sm">
                      {isOrderPlaced ? "Reserved · 4 left" : "In Stock · 5 units"}
                    </span>
                    {isOrderPlaced && (
                      <span className="inline-flex items-center gap-1 rounded bg-blue-100 px-2 py-0.5 text-[10px] font-bold text-blue-700">
                        <CheckCircle2 size={11} />
                        Order #BX-9042 Created
                      </span>
                    )}
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Live Synchronized KPI Metrics */}
        <div className="mt-4 grid grid-cols-3 gap-2.5 border-t border-blue-100 pt-4">
          {[
            {
              k: "Orders today",
              v: isOrderPlaced ? "13" : "12",
              delta: isOrderPlaced ? "+1 new" : "Live",
              highlight: isOrderPlaced,
            },
            {
              k: "Revenue",
              v: isOrderPlaced ? "PKR 62.8K" : "PKR 58K",
              delta: isOrderPlaced ? "+PKR 4,800" : "Updated",
              highlight: isOrderPlaced,
            },
            {
              k: "Replies sent",
              v: step >= 3 ? "48" : "47",
              delta: step >= 3 ? "+1 auto" : "99.8%",
              highlight: step >= 3,
            },
          ].map((s) => (
            <div
              key={s.k}
              className={`relative overflow-hidden rounded-xl border p-2.5 transition-all duration-500 ${
                s.highlight
                  ? "border-blue-200 bg-blue-50 shadow-[0_12px_25px_rgba(37,99,235,0.08)]"
                  : "border-blue-100 bg-slate-50"
              }`}
            >
              <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-slate-500">
                <span>{s.k}</span>
                <span
                  className={`text-[9px] font-semibold ${
                    s.highlight ? "text-blue-600" : "text-slate-400"
                  }`}
                >
                  {s.delta}
                </span>
              </div>
              <div className="mt-1 text-base font-black tracking-tight text-slate-950 md:text-lg">
                {s.v}
              </div>
            </div>
          ))}
        </div>
      </motion.div>

      {/* Floating Micro-Card 1: Answered in 2 seconds (preserves original text) */}
      <motion.div
        animate={{ y: [-3, 3, -3] }}
        transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
        className="absolute -bottom-5 -left-4 z-20 flex items-center gap-3 rounded-xl border border-blue-100 bg-white/95 px-4 py-2.5 shadow-xl shadow-blue-950/10 backdrop-blur-xl"
      >
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-gradient-to-tr from-blue-600 to-sky-400 text-white shadow-md">
          <Zap size={17} />
        </span>
        <div>
          <div className="text-xs font-bold text-slate-950">Answered in 2 seconds</div>
          <div className="text-[11px] font-medium text-slate-500">Even at 2am</div>
        </div>
      </motion.div>

      {/* Floating Micro-Card 2: WhatsApp Auto-Sync */}
      <motion.div
        animate={{ y: [3, -3, 3] }}
        transition={{ duration: 4.5, repeat: Infinity, ease: "easeInOut", delay: 1 }}
        className="absolute -right-3 -top-5 z-20 hidden items-center gap-2.5 rounded-xl border border-blue-100 bg-white/95 px-3.5 py-2 shadow-xl shadow-blue-950/10 backdrop-blur-xl sm:flex"
      >
        <span className="flex h-2 w-2 rounded-full bg-sky-300 ring-4 ring-sky-300/20" />
        <span className="text-xs font-semibold text-slate-950">WhatsApp Live Sync</span>
        <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[9px] font-bold text-blue-700">
          Connected
        </span>
      </motion.div>
    </div>
  );
}
