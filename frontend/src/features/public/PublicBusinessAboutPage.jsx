import { useParams } from "react-router-dom";

import {
  buildPublicSiteModel,
  FaqSection,
  PublicLoadingState,
  PublicUnavailableState,
  PublicWebsiteFrame,
  TestimonialsSection,
  usePublicBusinessSite,
} from "./publicWebsiteShared.jsx";

export function PublicBusinessAboutPage() {
  const { tenantSlug } = useParams();
  const { business, items, isLoading, error } = usePublicBusinessSite(tenantSlug, { limit: 8 });

  if (isLoading) {
    return <PublicLoadingState label="Loading about page..." />;
  }

  if (error && !business) {
    return <PublicUnavailableState title="Business unavailable" error={error} />;
  }

  const siteModel = buildPublicSiteModel(business, items);

  return (
    <PublicWebsiteFrame business={business} currentPage="about" siteModel={siteModel}>
      <div className="mx-auto max-w-6xl space-y-8 px-5 py-10">
        <section className="grid gap-5 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="rounded-[30px] border border-black/5 bg-white/92 p-6 shadow-sm">
            <div className="text-sm font-semibold uppercase tracking-[0.2em]" style={{ color: siteModel.theme.accent }}>About</div>
            <h1 className="mt-3 text-4xl font-semibold text-ink">{business.name}</h1>
            <p className="mt-4 text-base leading-8 text-slate-600">
              {business.description || "This business uses BizXusAI to present offers, guide customers, and move people into clear digital request flows."}
            </p>
          </div>
          <div className="rounded-[30px] border border-black/5 bg-white/92 p-6 shadow-sm">
            <div className="text-sm font-semibold uppercase tracking-[0.2em]" style={{ color: siteModel.theme.accent }}>Positioning</div>
            <div className="mt-4 space-y-3">
              {[
                siteModel.serviceLed ? "Service-led digital experience" : "Product-led digital storefront",
                `${siteModel.catalogLabel} organized into dedicated browsing pages`,
                "Customer requests routed into structured business workflows",
                "Built for direct conversion and repeat discovery",
              ].map((item) => (
                <div key={item} className="rounded-2xl border border-black/5 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700">
                  {item}
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="rounded-[30px] border border-black/5 bg-white/92 p-6 shadow-sm">
          <div className="text-sm font-semibold uppercase tracking-[0.2em]" style={{ color: siteModel.theme.accent }}>Why this site structure works</div>
          <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {[
              { title: "Discovery", text: "Customers get a cleaner path from first impression to deeper pages." },
              { title: "Trust", text: "About and contact details are no longer buried inside one long page." },
              { title: "Conversion", text: "Request actions sit on their own page so the CTA feels focused." },
              { title: "Scalability", text: "This category-based page structure can grow into a full website builder later." },
            ].map((card) => (
              <div key={card.title} className="rounded-2xl border border-black/5 bg-slate-50 p-4">
                <div className="text-lg font-semibold text-ink">{card.title}</div>
                <div className="mt-2 text-sm leading-6 text-slate-600">{card.text}</div>
              </div>
            ))}
          </div>
        </section>

        {business.websiteSettings?.testimonials?.length ? <TestimonialsSection testimonials={business.websiteSettings.testimonials} theme={siteModel.theme} /> : null}
        {business.websiteSettings?.faq?.length ? <FaqSection faq={business.websiteSettings.faq} theme={siteModel.theme} /> : null}
      </div>
    </PublicWebsiteFrame>
  );
}
