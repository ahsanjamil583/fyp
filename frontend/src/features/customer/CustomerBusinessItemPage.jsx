import { ProductImage } from "../../components/common/ProductImage.jsx";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowRight, Heart, MessageCircle, ShoppingCart } from "lucide-react";

import { WhatsAppAgentCta, WhatsAppAgentInfo } from "../../components/whatsapp/WhatsAppAgentCta.jsx";
import { addCartItem, addCustomerFavorite, getCustomerFavorites, getMarketplaceBusiness, getMarketplaceItem, removeCustomerFavorite, resolveUploadUrl } from "../../services/customerPortalApi.js";
import { getApiErrorMessage } from "../../services/apiError.js";

export function CustomerBusinessItemPage() {
  const { tenantSlug, itemId } = useParams();
  const [business, setBusiness] = useState(null);
  const [item, setItem] = useState(null);
  const [favorites, setFavorites] = useState([]);
  const [quantity, setQuantity] = useState(1);
  // Null means the item has no variants, or none has been picked yet.
  const [variantIndex, setVariantIndex] = useState(null);
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
        const variants = itemData?.variants || [];
        if (variants.length) {
          const defaultIndex = variants.findIndex((variant) => variant.isDefault);
          setVariantIndex(defaultIndex >= 0 ? defaultIndex : 0);
        }
        const favoriteData = await getCustomerFavorites();
        setFavorites(favoriteData);
      } catch (requestError) {
        setError(getApiErrorMessage(requestError, "Unable to load item."));
      }
    }
    load();
  }, [tenantSlug, itemId]);

  async function handleAdd() {
    setMessage("");
    setError("");
    try {
      await addCartItem({
        tenantId: business.id,
        itemId,
        // Clamped like the cart page. A free-text number field can send 0, a negative
        // or a decimal, all of which the API rejects with a 422 the customer never sees
        // explained.
        quantity: Math.max(1, Math.min(99, Math.floor(Number(quantity) || 1))),
        // Without this the choice was lost: the cart stored only the item, and checkout
        // fell back to whatever variant resolution considered the default.
        selectedVariantIndex: variantIndex,
      });
      setMessage(selectedVariant ? `Added ${selectedVariant.name} to cart.` : "Item added to cart.");
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to add item to cart."));
    }
  }

  async function toggleFavorite() {
    setError("");
    try {
      const exists = favorites.some((favorite) => favorite.item?.id === itemId && favorite.tenant?.id === business.id);
      const next = exists ? await removeCustomerFavorite(itemId, business.id) : await addCustomerFavorite({ tenantId: business.id, itemId });
      setFavorites(next);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to update your favourites."));
    }
  }

  const variants = item?.variants || [];
  const selectedVariant = variantIndex !== null && variants[variantIndex] ? variants[variantIndex] : null;
  const displayPrice = selectedVariant?.price ?? item?.price;

  if (error && !item) {
    return (
      <section className="space-y-4">
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">Item unavailable</h1>
        <p className="text-sm text-muted">{error}</p>
      </section>
    );
  }

  if (!item || !business) {
    return <section className="text-sm text-muted">Loading item...</section>;
  }

  return (
    <section className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_360px]">
      <div>
        <Link className="text-sm font-semibold text-brand" to={`/customer/businesses/${tenantSlug}`}>Back to {business.name}</Link>
        {item.images?.[0]?.url ? (
          <ProductImage alt="" className="mt-5 h-80 w-full rounded-xl object-cover" src={resolveUploadUrl(item.images[0].url)} />
        ) : (
          <div className="mt-5 h-80 rounded-xl bg-surface" />
        )}
        <h1 className="mt-6 text-3xl font-black tracking-tight text-ink md:text-4xl">{item.name}</h1>
        <p className="mt-4 text-base leading-7 text-muted">{item.description || "No description added."}</p>
        <div className="mt-6 grid gap-2 text-xs font-bold text-muted sm:grid-cols-3">
          {[
            ["1", "Check details"],
            ["2", "Choose quantity"],
            ["3", "Add to cart"],
          ].map(([n, label]) => (
            <div key={label} className="rounded-xl border border-line bg-white px-3 py-3 shadow-card">
              <span className="mr-2 inline-grid h-6 w-6 place-items-center rounded-full bg-brand text-xs text-white">{n}</span>
              {label}
            </div>
          ))}
        </div>
      </div>
      <div className="h-fit rounded-xl border border-line bg-white p-5 shadow-card">
        {message ? <div className="rounded-xl border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
        {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
        <div className="text-2xl font-semibold text-ink">{item.currency} {displayPrice}</div>
        {variants.length ? (
          <div className="mt-4">
            <label className="mb-1.5 block text-sm font-medium text-ink" htmlFor="variant">Options</label>
            <select
              id="variant"
              className="form-input"
              value={variantIndex ?? ""}
              onChange={(event) => setVariantIndex(event.target.value === "" ? null : Number(event.target.value))}
            >
              {variants.map((variant, index) => (
                <option key={variant.sku || variant.name || index} value={index}>
                  {variant.name || `Option ${index + 1}`}
                  {variant.price ? ` — ${item.currency} ${variant.price}` : ""}
                  {variant.stockStatus === "out_of_stock" ? " (out of stock)" : ""}
                </option>
              ))}
            </select>
          </div>
        ) : null}
        <div className="mt-4">
          <label className="mb-1.5 block text-sm font-medium text-ink" htmlFor="quantity">Quantity</label>
          <input id="quantity" className="form-input" min="1" type="number" value={quantity} onChange={(event) => setQuantity(event.target.value)} />
        </div>
        <button type="button" className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl border border-line px-4 py-2 text-sm font-semibold text-ink" onClick={toggleFavorite}>
          <Heart size={15} />
          {favorites.some((favorite) => favorite.item?.id === itemId && favorite.tenant?.id === business.id) ? "Saved to favorites" : "Save to favorites"}
        </button>
        <button type="button" className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white" onClick={handleAdd}>
          <ShoppingCart size={15} />
          Add to cart
        </button>
        <Link className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl border border-line bg-surface px-4 py-2 text-sm font-semibold text-ink" to="/customer/cart">
          Go to cart
          <ArrowRight size={15} />
        </Link>
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
        {business.enabledModuleCodes?.includes("ai_chat") ? (
          <Link className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-ink px-4 py-2 text-sm font-semibold text-white" to={`/customer/businesses/${tenantSlug}/chat`}>
            <MessageCircle size={15} />
            Ask AI about this item
          </Link>
        ) : null}
      </div>
    </section>
  );
}
