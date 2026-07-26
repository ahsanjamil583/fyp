import { Link, useParams } from "react-router-dom";

import { buildPublicSiteModel, ContactSection, PublicLoadingState, PublicUnavailableState, PublicWebsiteFrame, usePublicBusinessSite } from "./publicWebsiteShared.jsx";

export function PublicBusinessContactPage() {
  const { tenantSlug } = useParams();
  const { business, items, isLoading, error } = usePublicBusinessSite(tenantSlug, { limit: 6 });

  if (isLoading) {
    return <PublicLoadingState label="Loading contact page..." />;
  }

  if (error && !business) {
    return <PublicUnavailableState title="Business unavailable" error={error} />;
  }

  const siteModel = buildPublicSiteModel(business, items);

  return (
    <PublicWebsiteFrame business={business} currentPage="contact" siteModel={siteModel}>
      <div className="mx-auto max-w-6xl space-y-8 px-5 py-10">
        <ContactSection business={business} theme={siteModel.theme} />

        <section className="grid gap-5 lg:grid-cols-2">
          <div className="rounded-[30px] border border-black/5 bg-white/92 p-6 shadow-sm">
            <div className="text-sm font-semibold uppercase tracking-[0.2em]" style={{ color: siteModel.theme.accent }}>Quick actions</div>
            <div className="mt-4 space-y-3">
              <Link className="block rounded-2xl border border-black/5 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700" to={siteModel.catalogPath}>
                Browse {siteModel.catalogLabel}
              </Link>
              <Link className="block rounded-2xl border border-black/5 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700" to={`/businesses/${business.slug}/request`}>
                Go to {siteModel.requestLabel}
              </Link>
              {business.enabledModuleCodes?.includes("ai_chat") ? (
                <Link className="block rounded-2xl border border-black/5 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700" to={`/businesses/${business.slug}/chat`}>
                  Start AI Chat
                </Link>
              ) : null}
            </div>
          </div>
          <div className="rounded-[30px] border border-black/5 bg-white/92 p-6 shadow-sm">
            <div className="text-sm font-semibold uppercase tracking-[0.2em]" style={{ color: siteModel.theme.accent }}>Response style</div>
            <p className="mt-4 text-sm leading-7 text-slate-600">
              This business website is designed so customers can either contact directly, use the request page, or move into AI-guided engagement depending on the business type and enabled modules.
            </p>
          </div>
        </section>
      </div>
    </PublicWebsiteFrame>
  );
}
