import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { WhatsAppAgentCta, WhatsAppAgentInfo } from "../../components/whatsapp/WhatsAppAgentCta.jsx";
import { addCartItem, addCustomerFavorite, getCustomerFavorites, getMarketplaceBusiness, getMarketplaceItem, removeCustomerFavorite, resolveUploadUrl } from "../../services/customerPortalApi.js";

export function CustomerBusinessItemPage() {
  const { tenantSlug, itemId } = useParams();
  const [business, setBusiness] = useState(null);
  const [item, setItem] = useState(null);
  const [favorites, setFavorites] = useState([]);
  const [quantity, setQuantity] = useState(1);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      setError("");
      try {
        const [businessData, itemData] = await Promise.all([
          getMarketplaceBusiness(tenantSlug),
          getMarketplaceItem(tenantSlug, itemId),
        ]);
        setBusiness(businessData);
        setItem(itemData);
        const favoriteData = await getCustomerFavorites();
        setFavorites(favoriteData);
      } catch (requestError) {
        setError(requestError.response?.data?.detail || "Unable to load item.");
      }
    }
    load();
  }, [tenantSlug, itemId]);

  async function handleAdd() {
    setMessage("");
    setError("");
    try {
      await addCartItem({ tenantId: business.id, itemId, quantity: Number(quantity || 1) });
      setMessage("Item added to cart.");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to add item to cart.");
    }
  }

  async function toggleFavorite() {
    const exists = favorites.some((favorite) => favorite.item?.id === itemId && favorite.tenant?.id === business.id);
    const next = exists ? await removeCustomerFavorite(itemId, business.id) : await addCustomerFavorite({ tenantId: business.id, itemId });
    setFavorites(next);
  }

  if (error && !item) {
    return (
      <section className="space-y-4">
        <h1 className="text-3xl font-semibold text-ink">Item unavailable</h1>
        <p className="text-sm text-muted">{error}</p>
      </section>
    );
  }

  if (!item || !business) {
    return <section className="text-sm text-muted">Loading item...</section>;
  }

  return (
    <section className="grid gap-8 lg:grid-cols-[1fr_360px]">
      <div>
        <Link className="text-sm font-semibold text-brand" to={`/customer/businesses/${tenantSlug}`}>Back to {business.name}</Link>
        {item.images?.[0]?.url ? (
          <img alt="" className="mt-5 h-80 w-full rounded-md object-cover" src={resolveUploadUrl(item.images[0].url)} />
        ) : (
          <div className="mt-5 h-80 rounded-md bg-surface" />
        )}
        <h1 className="mt-6 text-4xl font-semibold text-ink">{item.name}</h1>
        <p className="mt-4 text-base leading-7 text-muted">{item.description || "No description added."}</p>
      </div>
      <div className="h-fit rounded-md border border-line bg-white p-5 shadow-sm">
        {message ? <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
        {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
        <div className="text-2xl font-semibold text-ink">{item.currency} {item.price}</div>
        <div className="mt-4">
          <label className="mb-1.5 block text-sm font-medium text-ink">Quantity</label>
          <input className="form-input" min="1" type="number" value={quantity} onChange={(event) => setQuantity(event.target.value)} />
        </div>
        <button className="mt-4 w-full rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink" onClick={toggleFavorite}>
          {favorites.some((favorite) => favorite.item?.id === itemId && favorite.tenant?.id === business.id) ? "Saved to favorites" : "Save to favorites"}
        </button>
        <button className="mt-4 w-full rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white" onClick={handleAdd}>
          Add to cart
        </button>
        <div className="mt-4">
          <WhatsAppAgentCta
            agent={business.whatsappAgent}
            className="w-full"
            message={`Hello, I found your business on BizXusAI and I want to ask about ${item.name}.`}
          />
        </div>
        <div className="mt-4">
          <WhatsAppAgentInfo agent={business.whatsappAgent} />
        </div>
      </div>
    </section>
  );
}
