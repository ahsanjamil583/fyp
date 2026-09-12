import { ProductImage } from "../../components/common/ProductImage.jsx";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowRight, Bot, Search, ShoppingCart, Store } from "lucide-react";

import { WhatsAppAgentCta, WhatsAppAgentInfo } from "../../components/whatsapp/WhatsAppAgentCta.jsx";
import { addCartItem, addCustomerFavorite, getCustomerFavorites, getMarketplaceBusiness, getMarketplaceItems, removeCustomerFavorite, resolveUploadUrl } from "../../services/customerPortalApi.js";
import { formatApiError } from "../../utils/apiErrors.js";

export function CustomerBusinessPage() {
  const { tenantSlug } = useParams();
  const [business, setBusiness] = useState(null);
  const [favorites, setFavorites] = useState([]);
  const [items, setItems] = useState([]);
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      setError("");
      try {
        const [businessData, itemData] = await Promise.all([
          getMarketplaceBusiness(tenantSlug),
          getMarketplaceItems(tenantSlug, { page: 1, limit: 20 }),
        ]);
        setBusiness(businessData);
        setItems(itemData.items);
        const favoriteData = await getCustomerFavorites();
        setFavorites(favoriteData);
      } catch (requestError) {
        setError(formatApiError(requestError.response?.data?.detail, "Unable to load marketplace business."));
      }
    }
    load();
  }, [tenantSlug]);

  async function searchItems(event) {
    event.preventDefault();
    const result = await getMarketplaceItems(tenantSlug, { search, page: 1, limit: 20 });
    setItems(result.items);
  }

  async function addToCart(itemId) {
    setMessage("");
    setError("");
    try {
      await addCartItem({ tenantId: business.id, itemId, quantity: 1 });
      setMessage("Item added to cart.");
    } catch (requestError) {
      setError(formatApiError(requestError.response?.data?.detail, "Unable to add item to cart."));
    }
  }

  async function toggleFavorite(itemId) {
    if (!business) return;
    const exists = favorites.some((favorite) => favorite.item?.id === itemId && favorite.tenant?.id === business.id);
    const next = exists ? await removeCustomerFavorite(itemId, business.id) : await addCustomerFavorite({ tenantId: business.id, itemId });
    setFavorites(next);
  }

  if (error && !business) {
    return (
      <section className="space-y-4">
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">Business unavailable</h1>
        <p className="text-sm text-muted">{error}</p>
      </section>
    );
  }

  if (!business) {
    return <section className="text-sm text-muted">Loading business...</section>;
  }

  return (
    <section className="space-y-6">
      <div className="rounded-2xl border border-line bg-surface-purple p-5 shadow-card">
        <Link className="text-sm font-semibold text-brand" to="/customer/marketplace">Back to marketplace</Link>
        <p className="mt-4 text-[11px] font-bold uppercase tracking-[0.16em] text-brand">Business</p>
        <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-ink">{business.name}</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-muted">{business.description || "Browse the available products and services below."}</p>
        <div className="mt-5 grid gap-2 text-xs font-bold text-muted sm:grid-cols-4">
          {[
            ["1", "Browse items"],
            ["2", "Ask questions"],
            ["3", "Add to cart"],
            ["4", "Checkout"],
          ].map(([n, label]) => (
            <div key={label} className="rounded-xl border border-line bg-white px-3 py-3">
              <span className="mr-2 inline-grid h-6 w-6 place-items-center rounded-full bg-brand text-xs text-white">{n}</span>
              {label}
            </div>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-3">
          {business.enabledModuleCodes?.includes("ai_chat") ? (
            <Link className="inline-flex rounded-xl bg-ink px-4 py-2 text-sm font-semibold text-white" to={`/customer/businesses/${tenantSlug}/chat`}>
              <Bot className="mr-2" size={16} />
              Open AI order chat
            </Link>
          ) : null}
          <WhatsAppAgentCta agent={business.whatsappAgent} />
        </div>
        <div className="mt-4 max-w-xl">
          <WhatsAppAgentInfo agent={business.whatsappAgent} />
        </div>
      </div>

      {message ? <div className="rounded-xl border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

      <form className="grid gap-3 rounded-xl border border-line bg-white p-5 shadow-card sm:grid-cols-[1fr_auto]" onSubmit={searchItems}>
        <label className="block">
          <span className="mb-1.5 flex items-center gap-1.5 text-sm font-bold text-ink"><Search size={15} /> Search this business</span>
          <input className="form-input" placeholder="Search products, services, sizes, colors..." value={search} onChange={(event) => setSearch(event.target.value)} />
        </label>
        <button className="rounded-xl bg-ink px-4 py-2 text-sm font-semibold text-white sm:mt-6">Search</button>
      </form>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => (
          <div key={item.id} className="rounded-xl border border-line bg-white p-4 shadow-card transition hover:-translate-y-0.5 hover:shadow-lift">
            <Link className="block" to={`/customer/businesses/${tenantSlug}/items/${item.id}`}>
              {item.images?.[0]?.url ? (
                <ProductImage alt="" className="mb-4 h-40 w-full rounded-xl object-cover" src={resolveUploadUrl(item.images[0].url)} />
              ) : (
                <div className="mb-4 h-40 rounded-xl bg-surface" />
              )}
              <div className="text-base font-bold text-ink">{item.name}</div>
            </Link>
            <p className="mt-2 line-clamp-2 text-sm text-muted">{item.description || "No description added."}</p>
            {item.serviceDetails?.durationMinutes ? (
              <div className="mt-2 text-xs font-semibold text-muted">{item.serviceDetails.durationMinutes} min service</div>
            ) : null}
            {item.variants?.length ? (
              <div className="mt-2 text-xs font-semibold text-muted">{item.variants.length} variants available</div>
            ) : null}
            {item.bundleComponents?.length ? (
              <div className="mt-2 text-xs font-semibold text-muted">{item.bundleComponents.length} items in bundle</div>
            ) : null}
            <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="text-sm font-semibold text-ink">{item.currency} {item.price}</div>
              <div className="flex flex-wrap gap-2">
                <Link className="rounded-xl border border-line px-3 py-1.5 text-sm font-semibold text-ink" to={`/customer/businesses/${tenantSlug}/items/${item.id}`}>
                  Details
                  <ArrowRight className="ml-1 inline" size={13} />
                </Link>
                <button type="button" className="rounded-xl border border-line px-3 py-1.5 text-sm font-semibold text-ink" onClick={() => toggleFavorite(item.id)}>
                  {favorites.some((favorite) => favorite.item?.id === item.id && favorite.tenant?.id === business.id) ? "Saved" : "Save"}
                </button>
                <button type="button" className="rounded-xl bg-brand px-3 py-1.5 text-sm font-semibold text-white" onClick={() => addToCart(item.id)}>
                  <ShoppingCart className="mr-1 inline" size={13} />
                  Add to cart
                </button>
              </div>
            </div>
          </div>
        ))}
        {!items.length ? (
          <div className="rounded-xl border border-dashed border-line bg-surface p-8 text-center md:col-span-2 xl:col-span-3">
            <Store className="mx-auto text-brand" size={30} />
            <div className="mt-3 font-bold text-ink">No items found</div>
            <p className="mt-1 text-sm text-muted">Try another search or ask the AI assistant what is available.</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}
