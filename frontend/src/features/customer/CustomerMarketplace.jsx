import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Bot, MapPin, Search, ShoppingBag, Store } from "lucide-react";

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
      <div className="rounded-2xl border border-line bg-surface-purple p-5 shadow-card">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">Marketplace</p>
            <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-ink">Find a business and start ordering</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
              Search by name or city, open a business, browse products or services, then use cart or AI chat to place an order.
            </p>
          </div>
          <div className="grid gap-2 text-xs font-bold text-muted sm:grid-cols-3 lg:min-w-[420px]">
            {[
              ["1", "Browse"],
              ["2", "Choose"],
              ["3", "Order"],
            ].map(([n, label]) => (
              <div key={label} className="rounded-xl border border-line bg-white px-3 py-3">
                <span className="mr-2 inline-grid h-6 w-6 place-items-center rounded-full bg-brand text-xs text-white">{n}</span>
                {label}
              </div>
            ))}
          </div>
        </div>
      </div>

      <form className="grid gap-3 rounded-xl border border-line bg-white p-5 shadow-card md:grid-cols-[1fr_220px_130px]" onSubmit={(event) => { event.preventDefault(); loadBusinesses(); }}>
        <label className="block">
          <span className="mb-1.5 flex items-center gap-1.5 text-sm font-bold text-ink"><Search size={15} /> Business or item</span>
          <input className="form-input" placeholder="Search businesses" value={search} onChange={(event) => setSearch(event.target.value)} />
        </label>
        <label className="block">
          <span className="mb-1.5 flex items-center gap-1.5 text-sm font-bold text-ink"><MapPin size={15} /> City</span>
          <input className="form-input" placeholder="Lahore, Karachi..." value={city} onChange={(event) => setCity(event.target.value)} />
        </label>
        <button className="rounded-xl bg-ink px-4 py-2 text-sm font-semibold text-white md:mt-6">Search</button>
      </form>

      {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

      <div className="flex items-center justify-between">
        <div className="text-sm text-muted">{meta.total || 0} businesses found.</div>
      </div>

      {favorites.length ? (
        <div className="rounded-xl border border-line bg-white p-5 shadow-card">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">Favorites</div>
              <div className="mt-1 text-base font-bold text-ink">Saved items for quick return</div>
            </div>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {favorites.slice(0, 6).map((favorite) => (
              <div key={favorite.id} className="rounded-xl border border-line bg-surface p-4">
                <Link className="font-semibold text-ink hover:text-brand" to={`/customer/businesses/${favorite.tenant?.slug}/items/${favorite.item?.id}`}>
                  {favorite.item?.name}
                </Link>
                <div className="mt-1 text-sm text-muted">{favorite.tenant?.name}</div>
                <div className="mt-3 flex gap-2">
                  <Link className="rounded-xl border border-line px-3 py-1.5 text-sm font-semibold text-ink" to={`/customer/businesses/${favorite.tenant?.slug}`}>
                    Open
                  </Link>
                  <button
                    className="rounded-xl border border-line px-3 py-1.5 text-sm font-semibold text-ink"
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
          <div key={business.id} className="rounded-xl border border-line bg-white p-5 shadow-card transition hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-lift">
            <Link className="block" to={`/customer/businesses/${business.slug}`}>
              <div className="flex items-start gap-3">
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand">
                  <Store size={20} />
                </span>
                <div className="min-w-0">
                  <div className="truncate text-lg font-bold text-ink">{business.name}</div>
                  <div className="mt-1 text-xs font-semibold capitalize text-muted">{business.websiteStatus}</div>
                </div>
              </div>
            </Link>
            <p className="mt-3 line-clamp-3 text-sm leading-6 text-muted">{business.description || "No description added."}</p>
            <div className="mt-4 flex flex-wrap gap-3 text-xs text-muted">
              <span>{business.address?.city || "Online"}</span>
              <span>{business.contact?.phone || ""}</span>
              {business.whatsappAgent?.enabled ? <span className="font-semibold text-emerald-700">WhatsApp available</span> : null}
              <span className="capitalize">{business.websiteStatus}</span>
            </div>
            <div className="mt-5 flex flex-wrap gap-2">
              <Link className="rounded-xl border border-line px-3 py-2 text-sm font-semibold text-ink" to={`/customer/businesses/${business.slug}`}>
                Open business
                <ArrowRight className="ml-1 inline" size={14} />
              </Link>
              {business.enabledModuleCodes?.includes("ai_chat") ? (
                <Link className="rounded-xl bg-brand px-3 py-2 text-sm font-semibold text-white" to={`/customer/businesses/${business.slug}/chat`}>
                  <Bot className="mr-1 inline" size={14} />
                  Ask AI
                </Link>
              ) : null}
              <WhatsAppAgentCta agent={business.whatsappAgent} compact />
            </div>
          </div>
        ))}
        {!businesses.length ? (
          <div className="rounded-xl border border-dashed border-line bg-surface p-8 text-center md:col-span-2 xl:col-span-3">
            <ShoppingBag className="mx-auto text-brand" size={30} />
            <div className="mt-3 font-bold text-ink">No businesses found</div>
            <p className="mt-1 text-sm text-muted">Try a different search or clear the city filter.</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}
