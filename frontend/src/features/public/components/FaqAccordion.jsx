import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Plus } from "lucide-react";

export function FaqAccordion({ items }) {
  const [openIndex, setOpenIndex] = useState(0);

  const toggle = (index) => {
    setOpenIndex((curr) => (curr === index ? -1 : index));
  };

  return (
    <motion.div
      className="grid gap-4"
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, amount: 0.22 }}
      variants={{
        hidden: {},
        show: {
          transition: {
            staggerChildren: 0.06,
          },
        },
      }}
    >
      {items.map((item, index) => {
        const isOpen = openIndex === index;

        return (
          <motion.div
            key={item.q}
            variants={{
              hidden: { opacity: 0, y: 16 },
              show: {
                opacity: 1,
                y: 0,
                transition: { duration: 0.38, ease: "easeOut" },
              },
            }}
            className={`overflow-hidden rounded-2xl border transition-all duration-300 ${
              isOpen
                ? "border-blue-400/50 bg-white shadow-lift ring-1 ring-blue-400/20"
                : "border-line bg-white/90 shadow-card hover:border-line hover:bg-white"
            }`}
          >
            <button
              type="button"
              onClick={() => toggle(index)}
              aria-expanded={isOpen}
              className="flex w-full items-center justify-between gap-4 p-5 text-left transition-colors md:p-6"
            >
              <span className="text-base font-bold tracking-tight text-ink md:text-lg">
                {item.q}
              </span>
              <motion.span
                animate={{ rotate: isOpen ? 45 : 0 }}
                transition={{ type: "spring", stiffness: 360, damping: 24 }}
                className={`grid h-8 w-8 shrink-0 place-items-center rounded-xl transition-colors ${
                  isOpen
                    ? "bg-blue-600 text-white shadow-sm"
                    : "border border-line bg-surface text-muted"
                }`}
              >
                <Plus size={16} strokeWidth={2.5} />
              </motion.span>
            </button>

            <AnimatePresence initial={false}>
              {isOpen && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                >
                  <div className="border-t border-line-soft px-5 pb-6 pt-3 md:px-6">
                    <motion.p
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ duration: 0.2, ease: "easeOut" }}
                      className="text-sm leading-7 text-muted md:text-base md:leading-8"
                    >
                      {item.a}
                    </motion.p>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        );
      })}
    </motion.div>
  );
}
