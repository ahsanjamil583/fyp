import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";

import { syncPublicStripeCheckout } from "../../services/publicWebsiteApi.js";
import {
  buildPublicSiteModel,
  CatalogSection,
  ContactSection,
  HeroSection,
  HighlightSection,
  PublicLoadingState,
  PublicUnavailableState,
  PublicWebsiteFrame,
  ServiceSection,
  TestimonialsSection,
  FaqSection,
  usePublicBusinessSite,
} from "./publicWebsiteShared.jsx";
import { getApiErrorMessage } from "../../services/apiError.js";

export function PublicBusinessPage() {
  const { tenantSlug } = useParams();
  const location = useLocation();
  const { business, items, meta, isLoading, error } = usePublicBusinessSite(tenantSlug, { limit: 8 });
  const [paymentMessage, setPaymentMessage] = useState("");
  const [paymentError, setPaymentError] = useState("");
  const syncedReturnRef = useRef("");

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.get("payment") === "stripe_success") {
      const transactionId = params.get("order") || "";
      const sessionId = params.get("session_id") || "";
      const syncKey = `${transactionId}:${sessionId || "return"}`;
      if (!transactionId || syncedReturnRef.current === syncKey) return;
      syncedReturnRef.current = syncKey;
      syncStripeReturn(transactionId, sessionId);
    }
    if (params.get("payment") === "stripe_cancelled") {
      setPaymentError("Stripe payment was cancelled. You can submit the request again or choose another payment method.");
    }
  }, [location.search]);

  async function syncStripeReturn(transactionId, sessionId) {
    setPaymentMessage("Stripe payment completed. Syncing payment status...");
    setPaymentError("");
    try {
      const data = await syncPublicStripeCheckout(tenantSlug, transactionId, { sessionId });
      if (data.providerStatus === "paid") {
        setPaymentMessage("Stripe payment confirmed. The business has received your paid order.");
      } else {
        setPaymentMessage(`Stripe checkout was checked. Current Stripe status: ${data.providerStatus || "pending"}.`);
      }
    } catch (requestError) {
      setPaymentError(getApiErrorMessage(requestError, "Stripe payment completed, but we could not sync the status yet. It may update when the webhook arrives."));
      setPaymentMessage("");
    }
  }

  if (isLoading) {
    return <PublicLoadingState label="Loading published website..." />;
  }

  if (error && !business) {
    return <PublicUnavailableState title="Business unavailable" error={error} />;
  }

  const siteModel = buildPublicSiteModel(business, items);
  const featuredCatalog = siteModel.products.length ? siteModel.products.slice(0, 3) : items.slice(0, 3);
  const featuredServices = siteModel.services.slice(0, 3);

  return (
    <PublicWebsiteFrame business={business} currentPage="home" siteModel={siteModel}>
      <HeroSection
        business={business}
        hero={siteModel.hero}
        primaryCtaLabel={siteModel.requestLabel}
        primaryCtaLink={`/businesses/${business.slug}/request`}
        secondaryCtaLabel={`Browse ${siteModel.catalogLabel}`}
        secondaryCtaLink={siteModel.catalogPath}
        serviceLed={siteModel.serviceLed}
        theme={siteModel.theme}
      />

      <div className="mx-auto max-w-6xl space-y-8 px-5 py-10">
        {paymentMessage ? <div className="rounded-2xl border border-green-200 bg-green-50 px-4 py-3 text-sm font-semibold text-green-800">{paymentMessage}</div> : null}
        {paymentError ? <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-800">{paymentError}</div> : null}

        <HighlightSection highlights={siteModel.highlights} theme={siteModel.theme} />

        <section className="grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="rounded-[30px] border border-black/5 bg-white/92 p-6 shadow-card">
            <div className="text-sm font-semibold uppercase tracking-[0.2em]" style={{ color: siteModel.theme.accent }}>Overview</div>
            <h2 className="mt-3 text-2xl font-extrabold tracking-tight text-ink">A better category-based public website</h2>
            <p className="mt-3 text-sm leading-7 text-slate-600">
              This homepage now focuses on clarity, trust, and conversion. Customers can discover the business here, then move into dedicated pages for {siteModel.catalogLabel.toLowerCase()}, contact, and direct requests.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link className="rounded-full px-5 py-3 text-sm font-semibold text-white" style={{ backgroundColor: siteModel.theme.accent }} to={siteModel.catalogPath}>
                Explore {siteModel.catalogLabel}
              </Link>
              <Link className="rounded-full border border-black/10 bg-white px-5 py-3 text-sm font-semibold text-ink" to={`/businesses/${business.slug}/about`}>
                About this business
              </Link>
            </div>
          </div>
          <div className="rounded-[30px] border border-black/5 bg-white/92 p-6 shadow-card">
            <div className="text-sm font-semibold uppercase tracking-[0.2em]" style={{ color: siteModel.theme.accent }}>Next Actions</div>
            <div className="mt-4 space-y-3">
              {[
                `${siteModel.catalogLabel} page for focused browsing`,
                "About page for trust and positioning",
                "Contact page for quick outreach",
                `${siteModel.requestLabel} page for clean conversion flow`,
              ].map((item) => (
                <div key={item} className="rounded-2xl border border-black/5 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700">
                  {item}
                </div>
              ))}
            </div>
          </div>
        </section>

        {featuredCatalog.length ? (
          <CatalogSection
            items={featuredCatalog}
            meta={{ total: meta.total || featuredCatalog.length }}
            search=""
            searchItems={(event) => event.preventDefault()}
            setSearch={() => {}}
            tenantSlug={tenantSlug}
            theme={siteModel.theme}
            title={`Featured ${siteModel.catalogLabel}`}
            showSearch={false}
          />
        ) : null}

        {siteModel.serviceLed && featuredServices.length ? (
          <ServiceSection items={featuredServices} tenantSlug={tenantSlug} theme={siteModel.theme} />
        ) : null}

        {siteModel.visibleSections.some((section) => section.type === "testimonials") ? (
          <TestimonialsSection testimonials={business.websiteSettings?.testimonials || []} theme={siteModel.theme} />
        ) : null}
        {siteModel.visibleSections.some((section) => section.type === "faq") ? (
          <FaqSection faq={business.websiteSettings?.faq || []} theme={siteModel.theme} />
        ) : null}

        <ContactSection business={business} theme={siteModel.theme} />
      </div>
    </PublicWebsiteFrame>
  );
}
