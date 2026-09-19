import { motion } from "framer-motion";

const TONE_STYLES = {
  violet: {
    bg: "bg-blue-950 text-sky-100",
    border: "group-hover:border-blue-500/35",
    glow: "from-blue-500/10",
    iconGlow: "group-hover:shadow-[0_0_20px_rgba(37,99,235,0.22)]",
  },
  purple: {
    bg: "bg-blue-100 text-blue-700",
    border: "group-hover:border-blue-400/35",
    glow: "from-blue-500/10",
    iconGlow: "group-hover:shadow-[0_0_20px_rgba(37,99,235,0.22)]",
  },
  green: {
    bg: "bg-sky-100 text-sky-700",
    border: "group-hover:border-sky-400/35",
    glow: "from-sky-500/10",
    iconGlow: "group-hover:shadow-[0_0_20px_rgba(14,165,233,0.22)]",
  },
  blue: {
    bg: "bg-sky-500/10 text-sky-600",
    border: "group-hover:border-sky-400/35",
    glow: "from-sky-500/10",
    iconGlow: "group-hover:shadow-[0_0_20px_rgba(56,189,248,0.22)]",
  },
  orange: {
    bg: "bg-indigo-100 text-indigo-700",
    border: "group-hover:border-indigo-400/35",
    glow: "from-indigo-500/10",
    iconGlow: "group-hover:shadow-[0_0_20px_rgba(79,70,229,0.2)]",
  },
};

/**
 * Premium interactive AI SaaS feature card with gradient borders,
 * hover lift, and animated icon dynamics.
 */
export function FeatureCard({ icon: Icon, tone, title, text, index = 0 }) {
  const style = TONE_STYLES[tone] || TONE_STYLES.purple;

  return (
    <motion.article
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.25, margin: "-30px" }}
      transition={{ duration: 0.5, delay: index * 0.06, ease: "easeOut" }}
      whileHover={{
        y: -5,
        transition: { duration: 0.28, ease: "easeOut" },
      }}
      className={`group relative overflow-hidden rounded-[1.4rem] border border-blue-100 bg-white p-7 shadow-card transition-all duration-300 hover:-translate-y-1 hover:shadow-xl ${style.border}`}
    >
      {/* Dynamic Hover Spotlight Glow */}
      <div
        className={`pointer-events-none absolute -right-20 -top-20 h-48 w-48 rounded-full bg-gradient-to-br ${style.glow} to-transparent opacity-0 blur-2xl transition-opacity duration-500 group-hover:opacity-100`}
      />

      {/* Top subtle specular line on hover */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[2px] bg-gradient-to-r from-transparent via-blue-500/0 to-transparent transition-all duration-300 group-hover:via-blue-500/40" />

      {/* Animated Icon Box */}
      <div
        className={`relative grid h-14 w-14 place-items-center rounded-2xl ${style.bg} transition-all duration-300 group-hover:scale-105 ${style.iconGlow}`}
      >
        <Icon
          size={26}
          strokeWidth={2}
          className="transition-transform duration-300 group-hover:scale-105"
        />
      </div>

      {/* Content */}
      <h3 className="mt-5 text-xl font-extrabold tracking-tight text-ink transition-colors duration-200 group-hover:text-blue-700">
        {title}
      </h3>
      <p className="mt-2.5 text-sm leading-7 text-muted">{text}</p>
    </motion.article>
  );
}
