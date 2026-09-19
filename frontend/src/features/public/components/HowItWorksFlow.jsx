import { motion } from "framer-motion";
import { Check, Rocket, Sparkles, Store, Tag } from "lucide-react";

const STEP_PREVIEWS = [
  {
    icon: Store,
    badge: "Smart Setup",
    detail: "Category: Retail & Fashion · 4 Modules suggested",
  },
  {
    icon: Tag,
    badge: "Catalog Auto-Sync",
    detail: "Photos, prices & inventory live in 1 tap",
  },
  {
    icon: Rocket,
    badge: "Storefront Live",
    detail: "AI Assistant responding · Taking orders",
  },
];

export function HowItWorksFlow({ steps }) {
  return (
    <motion.div
      className="relative mt-16"
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, amount: 0.22 }}
      variants={{
        hidden: {},
        show: {
          transition: {
            staggerChildren: 0.1,
          },
        },
      }}
    >
      {/* Animated Connecting SVG Laser Beam across steps (Desktop) */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute left-[15%] right-[15%] top-10 hidden md:block"
      >
        <motion.svg
          className="h-4 w-full"
          preserveAspectRatio="none"
          initial={{ opacity: 0, scaleX: 0 }}
          whileInView={{ opacity: 1, scaleX: 1 }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{ duration: 0.65, delay: 0.1, ease: "easeOut" }}
          style={{ originX: 0.5 }}
        >
          {/* Base inactive line */}
          <line
            x1="0%"
            y1="50%"
            x2="100%"
            y2="50%"
            stroke="#E5E9F3"
            strokeWidth="2"
            strokeDasharray="6 6"
          />
          {/* Animated flowing laser pulse */}
          <line
            x1="0%"
            y1="50%"
            x2="100%"
            y2="50%"
            stroke="#2563EB"
            strokeWidth="2.5"
            className="ai-laser-flow"
          />
        </motion.svg>
      </div>

      <div className="grid gap-8 md:grid-cols-3">
        {steps.map((s, index) => {
          const preview = STEP_PREVIEWS[index];
          const Icon = preview.icon;

          return (
            <motion.div
              key={s.n}
              variants={{
                hidden: {
                  opacity: 0,
                  y: 26,
                },
                show: {
                  opacity: 1,
                  y: 0,
                  transition: { duration: 0.5, ease: "easeOut" },
                },
              }}
              whileHover={{ y: -4, transition: { duration: 0.25 } }}
              className="group relative flex flex-col items-center text-center"
            >
              {/* Glowing Step Number Badge */}
              <div className="relative">
                <div className="ai-glow-animate absolute -inset-2 rounded-full bg-blue-500/20 blur-md opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
                <motion.span
                  className="relative grid h-16 w-16 place-items-center rounded-2xl bg-gradient-to-tr from-blue-700 to-sky-500 text-xl font-black text-white shadow-[0_10px_25px_-5px_rgba(37,99,235,0.35)] ring-4 ring-white transition-transform duration-300 group-hover:scale-110"
                >
                  {s.n}
                </motion.span>
              </div>

              {/* Step Card Container */}
              <div className="mt-6 flex w-full flex-1 flex-col justify-between rounded-[1.4rem] border border-blue-100 bg-white p-6 shadow-card transition-all duration-300 hover:border-blue-400/35 hover:shadow-xl">
                <div>
                  <div className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 px-3 py-1 text-xs font-bold text-brand">
                    <Sparkles size={12} />
                    Step {s.n}
                  </div>
                  <h3 className="mt-3 text-xl font-extrabold text-ink transition-colors duration-200 group-hover:text-brand">
                    {s.title}
                  </h3>
                  <p className="mt-2.5 text-sm leading-7 text-muted">{s.text}</p>
                </div>

                {/* Micro-preview chip inside step */}
                <div className="mt-6 flex items-center gap-2.5 rounded-xl border border-line-soft bg-surface p-3 text-left">
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-white text-brand shadow-sm">
                    <Icon size={18} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1 text-[11px] font-bold text-ink">
                      <span>{preview.badge}</span>
                      <Check size={12} className="text-blue-600" strokeWidth={3} />
                    </div>
                    <div className="truncate text-[11px] text-muted">{preview.detail}</div>
                  </div>
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>
    </motion.div>
  );
}
