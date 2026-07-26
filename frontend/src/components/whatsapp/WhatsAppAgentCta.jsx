function normalizePhone(value) {
  const raw = String(value || "").trim();
  let phone = raw.replace(/[^0-9+]/g, "");
  if (phone.startsWith("00")) phone = `+${phone.slice(2)}`;
  if (phone && !phone.startsWith("+")) {
    if (phone.startsWith("0") && phone.length >= 10) {
      phone = `+92${phone.slice(1)}`;
    } else if (phone.startsWith("92")) {
      phone = `+${phone}`;
    }
  }
  return phone;
}

function buildWhatsAppLink(agent, message) {
  const target = normalizePhone(agent?.normalizedBusinessWhatsAppNumber || agent?.businessWhatsAppNumber);
  const digits = target.replace(/\D/g, "");
  if (!digits) return "";
  const text = encodeURIComponent(message || "Hello, I found your business on BizXusAI and I want to ask about your products.");
  return `https://wa.me/${digits}?text=${text}`;
}

export function WhatsAppAgentCta({ agent, className = "", compact = false, themeColor = "", message = "" }) {
  const href = buildWhatsAppLink(agent, message);
  if (!agent?.enabled || !href) return null;
  const label = compact ? "WhatsApp" : "Message Business on WhatsApp";
  const style = themeColor ? { backgroundColor: themeColor } : undefined;
  const defaultClasses = themeColor
    ? "inline-flex items-center justify-center rounded-full px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:opacity-90"
    : "inline-flex items-center justify-center rounded-md bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700";

  return (
    <a className={`${defaultClasses} ${className}`} href={href} rel="noreferrer" target="_blank" style={style}>
      {label}
    </a>
  );
}

export function WhatsAppAgentInfo({ agent }) {
  if (!agent?.businessWhatsAppNumber && !agent?.normalizedBusinessWhatsAppNumber) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
        <div className="font-semibold">WhatsApp number not added</div>
        <div className="mt-2 text-xs leading-5 text-amber-800">
          This business has not added a WhatsApp number yet.
        </div>
      </div>
    );
  }
  if (!agent?.enabled) return null;
  return (
    <div className="rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
      <div className="font-semibold">Chat with business on WhatsApp</div>
      <div className="mt-1 text-emerald-800">{agent.businessWhatsAppNumber || agent.normalizedBusinessWhatsAppNumber}</div>
      <div className="mt-2 text-xs leading-5 text-emerald-700">{agent.messageHint}</div>
    </div>
  );
}
