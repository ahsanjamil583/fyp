import bizxusLogo from "../../assets/bizxus-logo.png";

export function BrandLogo({ className = "", imageClassName = "", labelClassName = "", showWordmark = true }) {
  return (
    <div className={`flex items-center gap-3 ${className}`.trim()}>
      <img
        src={bizxusLogo}
        alt="BizxusAI logo"
        className={`h-11 w-11 rounded-xl border border-slate-200/80 bg-white/92 p-1.5 object-contain shadow-[0_10px_24px_rgba(15,23,42,0.08)] ${imageClassName}`.trim()}
      />
      {showWordmark ? <div className={`text-lg font-semibold tracking-tight text-ink ${labelClassName}`.trim()}>BizxusAI</div> : null}
    </div>
  );
}
