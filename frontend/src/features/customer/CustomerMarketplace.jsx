import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { WhatsAppAgentCta } from "../../components/whatsapp/WhatsAppAgentCta.jsx";
import { getCustomerFavorites, getMarketplaceBusinesses, removeCustomerFavorite } from "../../services/customerPortalApi.js";

export function CustomerMarketplace() {
  const [businesses, setBusinesses] = useState([]);
  const [favorites, setFavorites] = useState([]);
  const [meta, setMeta] = useState({});
  const [search, setSearch] = useState("");
  const [city, setCity] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    loadBusinesses();
    getCustomerFavorites().then(setFavorites).catch(() => setFavorites([]));
  }, []);

  async function loadBusinesses(nextSearch = search, nextCity = city) {
    setError("");
    try {
      const result = await getMarketplaceBusinesses({ search: nextSearch, city: nextCity, page: 1, limit: 12 });
      setBusinesses(result.items);
      setMeta(result.meta);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to load marketplace.");
    }
  }

  return (
    <section className="space-y-6">
      <div className="border-b border-line pb-6">
        <p className="text-sm font-semibold uppercase tracking-wide text-brand">Marketplace</p>
        <h1 className="mt-2 text-3xl font-semibold text-ink">Published Businesses</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">Browse published businesses, compare offerings, and order from your customer portal.</p>
      </div>

      <form className="grid gap-3 rounded-md border border-line bg-white p-5 shadow-sm md:grid-cols-[1fr_240px_120px]" onSubmit={(event) => { event.preventDefault(); loadBusinesses(); }}>
        <input className="form-input" placeholder="Search businesses" value={search} onChange={(event) => setSearch(event.target.value)} />
        <input className="form-input" placeholder="City" value={city} onChange={(event) => setCity(event.target.value)} />
        <button className="rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white">Search</button>
      </form>

      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

      <div className="flex items-center justify-between">
        <div className="text-sm text-muted">{meta.total || 0} businesses found.</div>
      </div>

      {favorites.length ? (
        <div className="rounded-md border border-line bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold uppercase tracking-wide text-brand">Favorites</div>
              <div className="mt-1 text-lg font-semibold text-ink">Saved items for quick return</div>
            </div>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {favorites.slice(0, 6).map((favorite) => (
              <div key={favorite.id} className="rounded-md border border-line bg-surface p-4">
                <Link className="font-semibold text-ink hover:text-brand" to={`/customer/businesses/${favorite.tenant?.slug}/items/${favorite.item?.id}`}>
                  {favorite.item?.name}
                </Link>
                <div className="mt-1 text-sm text-muted">{favorite.tenant?.name}</div>
                <div className="mt-3 flex gap-2">
                  <Link className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink" to={`/customer/businesses/${favorite.tenant?.slug}`}>
                    Open
                  </Link>
                  <button
                    className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink"
                    onClick={async () => setFavorites(await removeCustomerFavorite(favorite.item.id, favorite.tenant.id))}
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {businesses.map((business) => (
          <div key={business.id} className="rounded-md border border-line bg-white p-5 shadow-sm transition hover:border-blue-200">
            <Link className="block" to={`/customer/businesses/${business.slug}`}>
              <div className="text-xl font-semibold text-ink">{business.name}</div>
            </Link>
            <p className="mt-3 line-clamp-3 text-sm leading-6 text-muted">{business.description || "No description added."}</p>
            <div className="mt-4 flex flex-wrap gap-3 text-xs text-muted">
              <span>{business.address?.city || "Online"}</span>
              <span>{business.contact?.phone || ""}</span>
              {business.whatsappAgent?.enabled ? <span className="font-semibold text-emerald-700">WhatsApp available</span> : null}
              <span className="capitalize">{business.websiteStatus}</span>
            </div>
            <div className="mt-5 flex flex-wrap gap-2">
              <Link className="rounded-md border border-line px-3 py-2 text-sm font-semibold text-ink" to={`/customer/businesses/${business.slug}`}>
                Open business
              </Link>
              <WhatsAppAgentCta agent={business.whatsappAgent} compact />
            </div>
          </div>
        ))}
        {!businesses.length ? (
          <div className="rounded-md border border-dashed border-line bg-surface p-6 text-sm text-muted md:col-span-2 xl:col-span-3">
            No published businesses available yet.
          </div>
        ) : null}
      </div>
    </section>
  );
}
