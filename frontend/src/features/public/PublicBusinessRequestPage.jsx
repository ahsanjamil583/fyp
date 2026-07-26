import { useParams } from "react-router-dom";

import { buildPublicSiteModel, PublicLoadingState, PublicTransactionSection, PublicUnavailableState, PublicWebsiteFrame, usePublicBusinessSite } from "./publicWebsiteShared.jsx";

export function PublicBusinessRequestPage() {
  const { tenantSlug } = useParams();
  const { business, items, isLoading, error } = usePublicBusinessSite(tenantSlug, { limit: 20 });

  if (isLoading) {
    return <PublicLoadingState label="Loading request page..." />;
  }

  if (error && !business) {
    return <PublicUnavailableState title="Business unavailable" error={error} />;
  }

  const siteModel = buildPublicSiteModel(business, items);

  return (
    <PublicWebsiteFrame business={business} currentPage="request" siteModel={siteModel}>
      <div className="mx-auto max-w-6xl space-y-8 px-5 py-10">
        <PublicTransactionSection
          business={business}
          tenantSlug={tenantSlug}
          items={items}
          theme={siteModel.theme}
          headline={siteModel.serviceLed ? "Send a booking or consultation request" : "Place an order or send a request"}
          description={
            siteModel.serviceLed
              ? "Use this dedicated request page to submit booking requests, service inquiries, or item-linked actions without crowding the homepage."
              : "Use this dedicated request page to place orders, ask about items, or send structured customer requests in one clean flow."
          }
        />
      </div>
    </PublicWebsiteFrame>
  );
}
