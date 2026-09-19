import { motion } from "framer-motion";

/**
 * Modern AI SaaS ambient background with soft radiant glows,
 * futuristic grid lines, and drifting particles.
 */
export function BackgroundGlow({ variant = "hero", className = "" }) {
  if (variant === "heroLight") {
    return (
      <div
        aria-hidden="true"
        className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}
      >
        <div className="ai-grid-light-bg absolute inset-0 opacity-75" />
        <div className="ai-glow-animate absolute -top-44 left-1/2 h-[520px] w-[760px] -translate-x-1/2 rounded-full bg-gradient-to-tr from-blue-100/80 via-sky-100/70 to-white blur-[120px]" />
        <div
          className="ai-glow-animate absolute top-36 right-8 h-[360px] w-[360px] rounded-full bg-blue-200/45 blur-[110px]"
          style={{ animationDelay: "-3.5s" }}
        />
        <div
          className="ai-glow-animate absolute bottom-[-120px] left-10 h-[420px] w-[420px] rounded-full bg-sky-100/70 blur-[120px]"
          style={{ animationDelay: "-5s" }}
        />
      </div>
    );
  }

  if (variant === "light") {
    return (
      <div
        aria-hidden="true"
        className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}
      >
        <div className="ai-grid-light-bg absolute inset-0 opacity-60" />
        <div className="ai-glow-animate absolute -top-40 left-1/2 h-[450px] w-[700px] -translate-x-1/2 rounded-full bg-gradient-to-tr from-brand-100/60 via-sky-100/40 to-transparent blur-[120px]" />
      </div>
    );
  }

  return (
    <div
      aria-hidden="true"
      className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}
    >
      {/* Precision Tech Grid */}
      <div className="ai-grid-bg absolute inset-0 opacity-80" />

      {/* Radiant Glow Orbs */}
      <div className="ai-glow-animate absolute -top-48 left-1/4 h-[520px] w-[520px] rounded-full bg-blue-600/25 blur-[130px]" />
      <div
        className="ai-glow-animate absolute top-20 right-10 h-[420px] w-[420px] rounded-full bg-sky-400/20 blur-[120px]"
        style={{ animationDelay: "-3.5s" }}
      />
      <div
        className="ai-glow-animate absolute bottom-[-100px] left-1/3 h-[460px] w-[460px] rounded-full bg-indigo-600/20 blur-[140px]"
        style={{ animationDelay: "-5s" }}
      />

      {/* Floating Micro-Particles */}
      <div className="absolute inset-0">
        {[
          { top: "18%", left: "15%", size: 4, delay: 0 },
          { top: "32%", left: "82%", size: 3, delay: 1.5 },
          { top: "64%", left: "28%", size: 5, delay: 2.2 },
          { top: "75%", left: "72%", size: 3, delay: 0.8 },
          { top: "45%", left: "50%", size: 4, delay: 3.1 },
        ].map((pt, i) => (
          <motion.span
            key={i}
            className="ai-particle-float absolute rounded-full bg-sky-300 shadow-[0_0_8px_rgba(56,189,248,0.8)]"
            style={{
              top: pt.top,
              left: pt.left,
              width: `${pt.size}px`,
              height: `${pt.size}px`,
              animationDelay: `${pt.delay}s`,
            }}
            animate={{
              opacity: [0.3, 0.9, 0.3],
              scale: [0.9, 1.3, 0.9],
            }}
            transition={{
              duration: 4 + (i % 3),
              repeat: Infinity,
              ease: "easeInOut",
              delay: pt.delay,
            }}
          />
        ))}
      </div>

      {/* Top subtle light beam edge */}
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-sky-400/40 to-transparent" />
    </div>
  );
}
