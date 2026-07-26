import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { BrandLogo } from "../../components/common/BrandLogo.jsx";
import { CustomerPaymentInstructions, getDefaultPaymentMethod } from "../../components/payments/CustomerPaymentInstructions.jsx";
import { WhatsAppAgentCta } from "../../components/whatsapp/WhatsAppAgentCta.jsx";
import { createPublicStripeCheckout, createPublicTransaction, getPublicBusiness, getPublicItems, resolveUploadUrl } from "../../services/publicWebsiteApi.js";
import { capitalize, formatTransactionLabel, formatTransactionSuccess, transactionTypeOptions } from "../../utils/transaction.js";
import { buildBusinessHighlights, buildWebsiteTheme, getVisibleSections } from "../public-website/websiteBuilderConfig.js";

export const emptyPublicRequest = {
  customerName: "",
  customerPhone: "",
  customerEmail: "",
  itemId: "",
  quantity: 1,
  transactionType: "auto",
  paymentMethod: "",
  fulfillmentType: "none",
  addressLine1: "",
  city: "",
  notes: "",
};

export function usePublicBusinessSite(tenantSlug, { limit = 12 } = {}) {
  const [business, setBusiness] = useState(null);
  const [items, setItems] = useState([]);
  const [meta, setMeta] = useState({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      setIsLoading(true);
      setError("");
      try {
        const [businessData, itemData] = await Promise.all([getPublicBusiness(tenantSlug), getPublicItems(tenantSlug, { page: 1, limit })]);
        setBusiness(businessData);
        setItems(itemData.items);
        setMeta(itemData.meta);
      } catch (requestError) {
        setError(requestError.response?.data?.detail || "Published business not found.");
      } finally {
        setIsLoading(false);
      }
    }

    load();
  }, [limit, tenantSlug]);

  async function loadItems(params = {}) {
    const result = await getPublicItems(tenantSlug, { page: 1, limit, ...params });
    setItems(result.items);
    setMeta(result.meta);
    return result;
  }

  return { business, items, meta, isLoading, error, setError, loadItems };
}

export function inferItemTransactionType(item) {
  return item?.isBookable || item?.itemType === "service" || item?.itemType === "bookable" ? "booking_request" : "order";
}

export function buildPublicSiteModel(business, items) {
  const websiteSettings = business?.websiteSettings || {};
  const theme = buildWebsiteTheme(websiteSettings);
  const highlights = buildBusinessHighlights(business, items);
  const visibleSections = getVisibleSections(websiteSettings);
  const services = items.filter((item) => inferItemTransactionType(item) === "booking_request");
  const products = items.filter((item) => inferItemTransactionType(item) !== "booking_request");
  const serviceLed = theme.templateCode === "service" || services.length > products.length;
  const catalogLabel = serviceLed ? "Services" : theme.templateCode === "catalog" ? "Menu" : "Offers";
  const catalogPath = serviceLed ? `/businesses/${business?.slug}/services` : `/businesses/${business?.slug}/items`;
  const requestLabel = serviceLed ? "Book Now" : "Order Now";
  const hero = websiteSettings.hero || {};

  return {
    theme,
    highlights,
    visibleSections,
    services,
    products,
    serviceLed,
    catalogLabel,
    catalogPath,
    requestLabel,
    hero,
  };
}

export function buildPublicSiteNav(business, siteModel) {
  const links = [
    { id: "home", label: "Home", to: `/businesses/${business.slug}` },
    { id: "catalog", label: siteModel.catalogLabel, to: siteModel.catalogPath },
    { id: "about", label: "About", to: `/businesses/${business.slug}/about` },
    { id: "contact", label: "Contact", to: `/businesses/${business.slug}/contact` },
    { id: "request", label: siteModel.requestLabel, to: `/businesses/${business.slug}/request` },
  ];
  if (business.enabledModuleCodes?.includes("ai_chat")) {
    links.push({ id: "chat", label: "AI Chat", to: `/businesses/${business.slug}/chat` });
  }
  return links;
}

export function PublicWebsiteFrame({ business, siteModel, currentPage, children }) {
  const navItems = useMemo(() => buildPublicSiteNav(business, siteModel), [business, siteModel]);

  return (
    <section style={{ background: siteModel.theme.background }}>
      <header className="sticky top-0 z-20 border-b border-black/5 bg-white/82 backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-4">
            <BrandLogo
              showWordmark={false}
              imageClassName="h-14 w-14 rounded-2xl border border-white/80 bg-white p-1.5 object-contain shadow-sm"
            />
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">BizXus public site</div>
              <div className="mt-1 text-2xl font-semibold tracking-tight text-ink">{business.name}</div>
              <div className="text-sm text-slate-500">
                {business.address?.city || "Online"} | {siteModel.serviceLed ? "Service-led experience" : "Storefront experience"}
              </div>
            </div>
          </div>
          <nav className="flex flex-wrap gap-2">
            {navItems.map((item) => (
              <Link
                key={item.id}
                className={
                  item.id === currentPage
                    ? "rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white shadow-sm"
                    : "rounded-full border border-black/10 bg-white/75 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-black/20 hover:text-ink"
                }
                to={item.to}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
      </header>
      {children}
      <footer className="border-t border-black/5 bg-white/84 backdrop-blur">
        <div className="mx-auto grid max-w-6xl gap-4 px-5 py-8 lg:grid-cols-[1fr_auto] lg:items-end">
          <div>
            <div className="text-sm font-semibold uppercase tracking-[0.22em]" style={{ color: siteModel.theme.accent }}>Powered by BizXusAI</div>
            <div className="mt-3 max-w-3xl text-sm leading-7 text-slate-600">
              A category-driven public website built for business discovery, AI-assisted engagement, and direct customer action across products, services, and requests.
            </div>
          </div>
          <div className="flex flex-wrap gap-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
            <span>{siteModel.catalogLabel}</span>
            <span>About</span>
            <span>Contact</span>
            <span>{siteModel.requestLabel}</span>
          </div>
        </div>
      </footer>
    </section>
  );
}

export function PublicLoadingState({ label = "Loading published website..." }) {
  return <section className="p-6 text-sm text-muted">{label}</section>;
}

export function PublicUnavailableState({ title, error }) {
  return (
    <section className="space-y-4 p-6">
      <h1 className="text-3xl font-semibold text-ink">{title}</h1>
      <p className="text-sm text-muted">{error}</p>
    </section>
  );
}

export function HeroSection({ business, hero, primaryCtaLabel, primaryCtaLink, secondaryCtaLabel, secondaryCtaLink, serviceLed, theme }) {
  return (
    <div className="border-b border-black/5">
      <div className="mx-auto grid max-w-6xl gap-8 px-5 py-12 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
        <div>
          <div className="inline-flex rounded-full border border-black/10 bg-white/80 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em]" style={{ color: theme.secondary }}>
            {serviceLed ? "Service Website" : "Public Storefront"}
          </div>
          <h1 className="mt-5 max-w-4xl text-4xl font-semibold leading-tight text-ink md:text-5xl">
            {hero.headline || `${business.name} made easy to browse, book, and contact online.`}
          </h1>
          <p className="mt-5 max-w-3xl text-base leading-7 text-slate-600">
            {hero.subheadline || business.description || "Explore offers, compare options, and take action from a clear business website built for modern browsing."}
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link className="rounded-full px-5 py-3 text-sm font-semibold text-white" style={{ backgroundColor: theme.accent }} to={primaryCtaLink}>
              {primaryCtaLabel}
            </Link>
            <Link className="rounded-full border border-black/10 bg-white/80 px-5 py-3 text-sm font-semibold text-ink" to={secondaryCtaLink}>
              {secondaryCtaLabel}
            </Link>
            <WhatsAppAgentCta agent={business.whatsappAgent} themeColor="#16a34a" />
          </div>
          <div className="mt-6 flex flex-wrap gap-3 text-sm text-slate-600">
            <span>{business.address?.city || "Online"}</span>
            <span>{business.contact?.phone || "Phone on request"}</span>
            <span>{business.contact?.email || "Email available after inquiry"}</span>
          </div>
          {business.enabledModuleCodes?.includes("ai_chat") ? (
            <div className="mt-5">
              <Link className="text-sm font-semibold underline underline-offset-4" style={{ color: theme.accent }} to={`/businesses/${business.slug}/chat`}>
                Open AI chat
              </Link>
            </div>
          ) : null}
        </div>
        <div className="grid gap-4">
          <div className="rounded-[28px] border border-black/5 bg-white/90 p-6 shadow-sm">
            <div className="text-sm font-semibold uppercase tracking-[0.2em]" style={{ color: theme.accent }}>About</div>
            <div className="mt-4 text-2xl font-semibold text-ink">{business.name}</div>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              {serviceLed
                ? "Lead with trust, clarity, and fast booking or inquiry flows for service-minded customers."
                : "Present your best items, bundles, and offers in a layout that feels curated rather than generic."}
            </p>
          </div>
          <div className="rounded-[28px] border border-black/5 p-6 text-white shadow-sm" style={{ backgroundColor: theme.secondary }}>
            <div className="text-sm uppercase tracking-[0.2em] text-white/70">Public Access</div>
            <div className="mt-4 text-3xl font-semibold">{business.websiteStatus === "published" ? "Live now" : "Preview mode"}</div>
            <div className="mt-3 text-sm leading-6 text-white/80">
              Customers can move from discovery to action through structured pages built for your business category.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function HighlightSection({ highlights, theme }) {
  return (
    <section>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        {highlights.slice(0, 5).map((item) => (
          <div key={item.label} className="rounded-[24px] border border-black/5 bg-white/85 p-5 shadow-sm">
            <div className="text-sm text-slate-500">{item.label}</div>
            <div className="mt-3 text-2xl font-semibold text-ink" style={{ color: theme.secondary }}>{item.value}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

export function CatalogSection({ items, meta, search, searchItems, setSearch, tenantSlug, theme, title, showSearch = true }) {
  return (
    <section id="public-offers" className="space-y-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="text-sm font-semibold uppercase tracking-[0.2em]" style={{ color: theme.accent }}>Browse</div>
          <h2 className="mt-2 text-3xl font-semibold text-ink">{title}</h2>
          <p className="mt-2 text-sm text-slate-600">{meta.total || 0} public offers available.</p>
        </div>
        {showSearch ? (
          <form className="flex gap-2 rounded-full border border-black/10 bg-white/90 p-2 shadow-sm" onSubmit={searchItems}>
            <input className="form-input min-w-64 border-0 bg-transparent shadow-none" placeholder="Search items" value={search} onChange={(event) => setSearch(event.target.value)} />
            <button className="rounded-full px-4 py-2 text-sm font-semibold text-white" style={{ backgroundColor: theme.accent }}>Search</button>
          </form>
        ) : null}
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => (
          <Link key={item.id} className="group rounded-[28px] border border-black/5 bg-white/90 p-4 shadow-sm transition hover:-translate-y-1 hover:shadow-md" to={`/businesses/${tenantSlug}/items/${item.id}`}>
            {item.images?.[0]?.url ? (
              <img alt="" className="mb-4 h-48 w-full rounded-[20px] object-cover" src={resolveUploadUrl(item.images[0].url)} />
            ) : (
              <div className="mb-4 h-48 rounded-[20px]" style={{ background: `linear-gradient(135deg, ${theme.accent}18, ${theme.secondary}12)` }} />
            )}
            <div className="text-lg font-semibold text-ink">{item.name}</div>
            <p className="mt-2 line-clamp-3 text-sm leading-6 text-slate-600">{item.description || "No description added."}</p>
            <div className="mt-4 flex items-center justify-between">
              <div className="text-sm font-semibold" style={{ color: theme.secondary }}>{item.currency} {item.price}</div>
              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 group-hover:text-slate-700">View</div>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}

export function ServiceSection({ items, tenantSlug, theme }) {
  if (!items.length) return null;
  return (
    <section className="space-y-5">
      <div>
        <div className="text-sm font-semibold uppercase tracking-[0.2em]" style={{ color: theme.accent }}>Services</div>
        <h2 className="mt-2 text-3xl font-semibold text-ink">Service-focused offers</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          Highlight duration, delivery mode, and booking-friendly offers for consultative or appointment-based businesses.
        </p>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        {items.slice(0, 6).map((item) => (
          <Link key={item.id} className="rounded-[28px] border border-black/5 bg-white/90 p-5 shadow-sm transition hover:-translate-y-1 hover:shadow-md" to={`/businesses/${tenantSlug}/items/${item.id}`}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-xl font-semibold text-ink">{item.name}</div>
                <div className="mt-2 text-sm text-slate-600">{item.description || "Service details available on the detail page."}</div>
              </div>
              <div className="rounded-full px-3 py-1 text-xs font-semibold text-white" style={{ backgroundColor: theme.secondary }}>
                {item.serviceDetails?.deliveryMode || "onsite"}
              </div>
            </div>
            <div className="mt-5 grid gap-3 md:grid-cols-3">
              <ServiceMetric label="Duration" value={`${item.serviceDetails?.durationMinutes || 0} min`} />
              <ServiceMetric label="Buffer" value={`${item.serviceDetails?.bufferMinutes || 0} min`} />
              <ServiceMetric label="Starting at" value={`${item.currency} ${item.price}`} />
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}

function ServiceMetric({ label, value }) {
  return (
    <div className="rounded-xl border border-black/5 bg-slate-50 px-4 py-3">
      <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{label}</div>
      <div className="mt-2 text-sm font-semibold text-ink">{value}</div>
    </div>
  );
}

export function TestimonialsSection({ testimonials, theme }) {
  if (!testimonials?.length) return null;
  return (
    <section className="space-y-5">
      <div>
        <div className="text-sm font-semibold uppercase tracking-[0.2em]" style={{ color: theme.accent }}>Social proof</div>
        <h2 className="mt-2 text-3xl font-semibold text-ink">What customers say</h2>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        {testimonials.map((item, index) => (
          <div key={`testimonial-${index}`} className="rounded-[24px] border border-black/5 bg-white/90 p-5 shadow-sm">
            <div className="text-base leading-7 text-slate-700">"{item.quote}"</div>
            <div className="mt-4 font-semibold text-ink">{item.name || "Customer"}</div>
            <div className="mt-1 text-sm text-slate-500">{item.role || "Verified feedback"}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

export function FaqSection({ faq, theme }) {
  if (!faq?.length) return null;
  return (
    <section className="space-y-5">
      <div>
        <div className="text-sm font-semibold uppercase tracking-[0.2em]" style={{ color: theme.accent }}>FAQ</div>
        <h2 className="mt-2 text-3xl font-semibold text-ink">Questions customers ask before deciding</h2>
      </div>
      <div className="space-y-3">
        {faq.map((item, index) => (
          <div key={`faq-${index}`} className="rounded-[24px] border border-black/5 bg-white/90 p-5 shadow-sm">
            <div className="text-lg font-semibold text-ink">{item.question}</div>
            <div className="mt-3 text-sm leading-6 text-slate-600">{item.answer}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

export function ContactSection({ business, theme }) {
  const whatsappAgent = business.whatsappAgent || {};
  const whatsappValue = whatsappAgent.businessWhatsAppNumber || business.contact?.whatsapp || "Not shared yet";
  return (
    <section className="rounded-[32px] border border-black/5 bg-white/90 p-6 shadow-sm">
      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <div className="text-sm font-semibold uppercase tracking-[0.2em]" style={{ color: theme.accent }}>Contact</div>
          <h2 className="mt-2 text-3xl font-semibold text-ink">Reach the business directly</h2>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Keep contact details easy to find for customers who prefer a quick call, WhatsApp message, or direct email before purchasing.
          </p>
        </div>
        <div className="grid gap-3">
          <ContactCard label="Phone" value={business.contact?.phone || "Not shared yet"} />
          <ContactCard label="Email" value={business.contact?.email || "Not shared yet"} />
          <ContactCard
            label={whatsappAgent.agentReady ? "WhatsApp AI Agent" : "WhatsApp"}
            value={whatsappValue}
            href={whatsappAgent.enabled ? whatsappAgent.waLink : ""}
          />
          <ContactCard label="Location" value={[business.address?.line1, business.address?.city, business.address?.province].filter(Boolean).join(", ") || "Online"} />
        </div>
      </div>
    </section>
  );
}

function ContactCard({ label, value, href = "" }) {
  return (
    <div className="rounded-xl border border-black/5 bg-slate-50 px-4 py-3">
      <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{label}</div>
      {href ? (
        <a className="mt-2 inline-flex text-sm font-semibold text-emerald-700 underline underline-offset-4" href={href} rel="noreferrer" target="_blank">
          {value}
        </a>
      ) : (
        <div className="mt-2 text-sm font-semibold text-ink">{value}</div>
      )}
    </div>
  );
}

export function PublicTransactionSection({ tenantSlug, business = {}, items, theme, headline, description }) {
  const [order, setOrder] = useState({ ...emptyPublicRequest, itemId: items[0]?.id || "" });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setOrder((current) => ({ ...current, itemId: current.itemId || items[0]?.id || "" }));
  }, [items]);

  const selectedItem = items.find((item) => item.id === order.itemId);
  const defaultRequestType = !selectedItem ? "inquiry" : inferItemTransactionType(selectedItem);
  const activeRequestType = order.transactionType === "auto" ? defaultRequestType : order.transactionType;

  async function submitOrder(event) {
    event.preventDefault();
    setMessage("");
    setError("");
    try {
      const created = await createPublicTransaction(tenantSlug, {
        customerName: order.customerName,
        customerPhone: order.customerPhone,
        customerEmail: order.customerEmail,
        transactionType: order.transactionType,
        paymentMethod: order.paymentMethod || getDefaultPaymentMethod(business.paymentOptions || {}),
        items: order.itemId ? [{ itemId: order.itemId, quantity: Number(order.quantity || 1) }] : [],
        fulfillment: {
          type: order.fulfillmentType,
          address: { line1: order.addressLine1, city: order.city },
        },
        notes: order.notes,
      });
      if ((order.paymentMethod || getDefaultPaymentMethod(business.paymentOptions || {})) === "stripe_test") {
        setMessage("Opening Stripe Checkout...");
        const checkout = await createPublicStripeCheckout(tenantSlug, created.id);
        if (checkout.checkoutUrl) {
          window.location.href = checkout.checkoutUrl;
          return;
        }
      }
      setMessage(formatTransactionSuccess({ ...created, transactionType: created.transactionType || activeRequestType }));
      setOrder((current) => ({ ...emptyPublicRequest, itemId: current.itemId || items[0]?.id || "" }));
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to submit request.");
    }
  }

  return (
    <section id="public-transaction-form" className="rounded-[32px] border border-black/5 bg-white/92 p-6 shadow-sm">
      <div className="grid gap-8 lg:grid-cols-[0.85fr_1.15fr]">
        <div>
          <div className="text-sm font-semibold uppercase tracking-[0.2em]" style={{ color: theme.accent }}>Take action</div>
          <h2 className="mt-3 text-3xl font-semibold text-ink">{headline || `Submit ${capitalize(formatTransactionLabel(activeRequestType))}`}</h2>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            {description || "Use one public form for direct orders, quote requests, booking requests, or general inquiries depending on what this business offers."}
          </p>
        </div>
        <form className="grid gap-3" onSubmit={submitOrder}>
          {message ? <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
          {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
          <div className="grid gap-3 md:grid-cols-2">
            <input className="form-input" required placeholder="Your name / Apna naam" value={order.customerName} onChange={(event) => setOrder((current) => ({ ...current, customerName: event.target.value }))} />
            <input className="form-input" required placeholder="03001234567" value={order.customerPhone} onChange={(event) => setOrder((current) => ({ ...current, customerPhone: event.target.value }))} />
          </div>
          <input className="form-input" placeholder="yourname@example.pk" value={order.customerEmail} onChange={(event) => setOrder((current) => ({ ...current, customerEmail: event.target.value }))} />
          <div className="grid gap-3 md:grid-cols-2">
            <select className="form-input" value={order.transactionType} onChange={(event) => setOrder((current) => ({ ...current, transactionType: event.target.value }))}>
              {transactionTypeOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
            <select className="form-input" value={order.itemId} onChange={(event) => setOrder((current) => ({ ...current, itemId: event.target.value }))}>
              <option value="">No item selected</option>
              {items.map((item) => (
                <option key={item.id} value={item.id}>{item.name} - {item.currency} {item.price}</option>
              ))}
            </select>
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            <input className="form-input" min="1" type="number" value={order.quantity} onChange={(event) => setOrder((current) => ({ ...current, quantity: event.target.value }))} />
            <select className="form-input" value={order.fulfillmentType} onChange={(event) => setOrder((current) => ({ ...current, fulfillmentType: event.target.value }))}>
              <option value="none">No delivery / walk-in</option>
              <option value="pickup">Pickup</option>
              <option value="delivery">Delivery</option>
            </select>
            <select className="form-input" value={order.city} onChange={(event) => setOrder((current) => ({ ...current, city: event.target.value }))}>
              <option value="">Select city / city likhein</option>
              {["Islamabad", "Rawalpindi", "Lahore", "Karachi", "Faisalabad", "Peshawar", "Quetta", "Multan", "Hyderabad"].map((city) => (
                <option key={city} value={city}>{city}</option>
              ))}
            </select>
          </div>
          <input className="form-input" placeholder="Address / Mohalla, street, block" value={order.addressLine1} onChange={(event) => setOrder((current) => ({ ...current, addressLine1: event.target.value }))} />
          <CustomerPaymentInstructions
            compact
            options={business.paymentOptions || {}}
            selectedMethod={order.paymentMethod || getDefaultPaymentMethod(business.paymentOptions || {})}
            onChange={(value) => setOrder((current) => ({ ...current, paymentMethod: value }))}
          />
          <textarea className="form-input min-h-28" placeholder="Notes: delivery timing, landmark, ya short request" value={order.notes} onChange={(event) => setOrder((current) => ({ ...current, notes: event.target.value }))} />
          <button className="rounded-full px-5 py-3 text-sm font-semibold text-white" style={{ backgroundColor: theme.accent }}>
            Submit {capitalize(formatTransactionLabel(activeRequestType))}
          </button>
        </form>
      </div>
    </section>
  );
}
