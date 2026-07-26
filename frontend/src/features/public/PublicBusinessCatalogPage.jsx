import { useState } from "react";
import { useParams } from "react-router-dom";

import {
  buildPublicSiteModel,
  CatalogSection,
  PublicLoadingState,
  PublicUnavailableState,
  PublicWebsiteFrame,
  ServiceSection,
  usePublicBusinessSite,
} from "./publicWebsiteShared.jsx";

export function PublicBusinessCatalogPage() {
  const { tenantSlug } = useParams();
  const { business, items, meta, isLoading, error, loadItems } = usePublicBusinessSite(tenantSlug, { limit: 18 });
  const [search, setSearch] = useState("");

  async function searchItems(event) {
    event.preventDefault();
    await loadItems({ search });
  }

  if (isLoading) {
    return <PublicLoadingState label="Loading public offers..." />;
  }

  if (error && !business) {
    return <PublicUnavailableState title="Business unavailable" error={error} />;
  }

  const siteModel = buildPublicSiteModel(business, items);

  return (
    <PublicWebsiteFrame business={business} currentPage="catalog" siteModel={siteModel}>
      <div className="mx-auto max-w-6xl space-y-8 px-5 py-10">
        {siteModel.serviceLed ? (
          <ServiceSection items={siteModel.services.length ? siteModel.services : items} tenantSlug={tenantSlug} theme={siteModel.theme} />
        ) : null}
        <CatalogSection
          items={siteModel.serviceLed ? siteModel.products : siteModel.products.length ? siteModel.products : items}
          meta={meta}
          search={search}
          searchItems={searchItems}
          setSearch={setSearch}
          tenantSlug={tenantSlug}
          theme={siteModel.theme}
          title={siteModel.serviceLed ? "Products and packages" : siteModel.catalogLabel}
        />
      </div>
    </PublicWebsiteFrame>
  );
}
