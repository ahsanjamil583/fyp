import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Bot,
  Check,
  ExternalLink,
  MapPin,
  Package,
  Search,
  ShoppingBag,
  ShoppingCart,
  Store,
  X,
} from "lucide-react";

import { ProductImage } from "../../components/common/ProductImage.jsx";
import { WhatsAppAgentCta } from "../../components/whatsapp/WhatsAppAgentCta.jsx";
import { getPublicBusinessCategories } from "../../services/businessCategoryApi.js";
import {
  addCartItem,
  getMarketplaceBusinesses,
  getMarketplaceCatalog,
} from "../../services/customerPortalApi.js";

/**
 * Customer marketplace.
 *
 * Products lead, businesses are secondary: a shopper should be able to browse and
 * filter everything on offer without first choosing a business. Each product still
 * names the business that sells it and links out to its published website.
 */

const EMPTY_FILTERS = { search: "", category: "", itemType: "", city: "" };

function formatPrice(item) {
  const price = Number(item?.price ?? 0);
  if (!price) return "Price on request";
  const currency = item?.currency || "PKR";
  return `${currency} ${price.toLocaleString()}`;
}

function availabilityOf(item) {
  const stock = item?.stock || {};
  if (stock.tracked === false || stock.status === "untracked") return { label: "Available", tone: "muted" };
  if (stock.inStock === false || stock.status === "out_of_stock") return { label: "Out of stock", tone: "out" };
  if (stock.status === "low_stock") return { label: "Low stock", tone: "low" };
  return { label: "In stock", tone: "in" };
}

const AVAILABILITY_STYLES = {
  in: "bg-green-50 text-green-600",
  low: "bg-orange-100 text-orange-600",
  out: "bg-red-50 text-red-600",
  muted: "bg-surface text-muted",
};

export function CustomerMarketplace() {
  const [tab, setTab] = useState("products");
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [catalog, setCatalog] = useState({ items: [], facets: {}, pagination: {} });
  const [businesses, setBusinesses] = useState([]);
  const [categories, setCategories] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [busyItemId, setBusyItemId] = useState("");

  useEffect(() => {
    getPublicBusinessCategories().then(setCategories).catch(() => setCategories([]));
  }, []);

  const loadCatalog = useCallback(async (next) => {
    setIsLoading(true);
    setError("");
    try {
      const data = await getMarketplaceCatalog({
        search: next.search,
        category: next.category,
        itemType: next.itemType,
        city: next.city,
        page: 1,
        limit: 24,
      });
      setCatalog(data);
    } catch {
      setError("We could not load the marketplace right now. Please try again.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadBusinesses = useCallback(async (next) => {
    try {
      const data = await getMarketplaceBusinesses({ search: next.search, city: next.city, page: 1, limit: 24 });
      setBusinesses(data.items || []);
    } catch {
      setBusinesses([]);
    }
  }, []);

  useEffect(() => {
    loadCatalog(EMPTY_FILTERS);
    loadBusinesses(EMPTY_FILTERS);
  }, [loadCatalog, loadBusinesses]);

  function applyFilters(next) {
    setFilters(next);
    loadCatalog(next);
    loadBusinesses(next);
  }

  function resetFilters() {
    applyFilters(EMPTY_FILTERS);
  }

  const categoryNameById = useMemo(
    () => Object.fromEntries(categories.map((category) => [category.id, category.name])),
    [categories],
  );

  async function quickAddToCart(item) {
    setBusyItemId(item.id);
    setError("");
    setNotice("");
    try {
      await addCartItem({ tenantId: item.business?.id, itemId: item.id, quantity: 1 });
      setNotice(`${item.name} added to your cart.`);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "We could not add that to your cart.");
    } finally {
      setBusyItemId("");
    }
  }

  const hasFilters = Object.values(filters).some(Boolean);
  const facets = catalog.facets || {};
  const products = catalog.items || [];

  return (
    <section className="space-y-6">
      {/* ------------------------------------------------------------ hero -- */}
      <div className="rounded-card border border-line bg-surface-purple p-5 sm:p-6">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">Marketplace</p>
        <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight text-ink">Shop local businesses</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
          Browse products and services from every published business. Filter by category, add to your
          cart, or ask a business a question before you order.
        </p>
      </div>

      {/* --------------------------------------------------------- filters -- */}
      <form
        className="rounded-card border border-line bg-white p-4 shadow-card sm:p-5"
        onSubmit={(event) => {
          event.preventDefault();
          applyFilters(filters);
        }}
      >
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto]">
          <label className="block">
            <span className="mb-1.5 flex items-center gap-1.5 text-xs font-bold text-ink">
              <Search size={14} /> Search
            </span>
            <input
              className="form-input"
              placeholder="Product, service or business"
              value={filters.search}
              onChange={(event) => setFilters({ ...filters, search: event.target.value })}
            />
          </label>

          <label className="block">
            <span className="mb-1.5 block text-xs font-bold text-ink">Category</span>
            <select
              className="form-input"
              value={filters.category}
              onChange={(event) => applyFilters({ ...filters, category: event.target.value })}
            >
              <option value="">All categories</option>
              {(facets.categories || []).map((category) => (
                <option key={category} value={category}>{category}</option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="mb-1.5 block text-xs font-bold text-ink">Type</span>
            <select
              className="form-input"
              value={filters.itemType}
              onChange={(event) => applyFilters({ ...filters, itemType: event.target.value })}
            >
              <option value="">Products &amp; services</option>
              {(facets.itemTypes || []).map((type) => (
                <option key={type} value={type} className="capitalize">{type}</option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="mb-1.5 flex items-center gap-1.5 text-xs font-bold text-ink">
              <MapPin size={14} /> City
            </span>
            <select
              className="form-input"
              value={filters.city}
              onChange={(event) => applyFilters({ ...filters, city: event.target.value })}
            >
              <option value="">Anywhere</option>
              {(facets.cities || []).map((city) => (
                <option key={city} value={city} className="capitalize">{city}</option>
              ))}
            </select>
          </label>

          <button type="submit" className="ui-btn-primary h-[42px] self-end">Search</button>
        </div>

        {hasFilters ? (
          <button type="button" onClick={resetFilters} className="mt-3 inline-flex items-center gap-1.5 text-xs font-bold text-brand hover:underline">
            <X size={13} /> Clear filters
          </button>
        ) : null}
      </form>

      {error ? (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">{error}</div>
      ) : null}
      {notice ? (
        <div role="status" className="flex items-center gap-2 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm font-semibold text-green-700">
          <Check size={15} /> {notice}
        </div>
      ) : null}

      {/* ------------------------------------------------------------ tabs -- */}
      <div className="flex items-center gap-1 border-b border-line">
        {[
          ["products", "Products & services", products.length],
          ["businesses", "Businesses", businesses.length],
        ].map(([key, label, count]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`-mb-px border-b-2 px-4 py-2.5 text-sm font-bold transition ${
              tab === key ? "border-brand text-brand" : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {label}
            <span className="ml-1.5 rounded-full bg-surface px-1.5 py-0.5 text-[11px]">{count}</span>
          </button>
        ))}
      </div>

      {/* -------------------------------------------------------- products -- */}
      {tab === "products" ? (
        isLoading ? (
          <div className="py-12 text-center text-sm text-muted">Loading products...</div>
        ) : products.length ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {products.map((item) => {
              const availability = availabilityOf(item);
              const business = item.business || {};
              const image = (item.images || [])[0]?.url || (item.images || [])[0];
              return (
                <article
                  key={`${business.slug}-${item.id}`}
                  className="flex flex-col overflow-hidden rounded-card border border-line bg-white shadow-card transition hover:-translate-y-0.5 hover:shadow-lift"
                >
                  <Link to={`/customer/businesses/${business.slug}/items/${item.id}`} className="block">
                    <ProductImage src={image} alt={item.name} className="h-40 w-full object-cover" />
                  </Link>

                  <div className="flex flex-1 flex-col p-4">
                    <div className="flex items-start justify-between gap-2">
                      <span className="rounded-full bg-brand-50 px-2 py-0.5 text-[11px] font-bold text-brand">
                        {item.categoryName || (item.itemType === "service" ? "Service" : "Product")}
                      </span>
                      <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${AVAILABILITY_STYLES[availability.tone]}`}>
                        {availability.label}
                      </span>
                    </div>

                    <Link
                      to={`/customer/businesses/${business.slug}/items/${item.id}`}
                      className="mt-2 line-clamp-2 text-base font-bold text-ink hover:text-brand"
                    >
                      {item.name}
                    </Link>

                    <div className="mt-1 text-lg font-extrabold text-ink">{formatPrice(item)}</div>

                    {/* The business name links to its published storefront. */}
                    <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
                      <Link
                        to={`/customer/businesses/${business.slug}`}
                        className="inline-flex items-center gap-1 font-bold text-brand hover:underline"
                      >
                        <Store size={12} /> {business.name}
                      </Link>
                      {business.city ? (
                        <span className="inline-flex items-center gap-1 capitalize">
                          <MapPin size={11} /> {business.city}
                        </span>
                      ) : null}
                    </div>

                    <div className="mt-auto flex flex-wrap gap-2 pt-4">
                      <button
                        type="button"
                        onClick={() => quickAddToCart(item)}
                        disabled={availability.tone === "out" || busyItemId === item.id}
                        className="ui-btn-primary flex-1 !py-2 !text-xs disabled:opacity-60"
                      >
                        <ShoppingCart size={14} />
                        {busyItemId === item.id ? "Adding..." : "Add to cart"}
                      </button>
                      <Link
                        to={`/customer/businesses/${business.slug}/items/${item.id}`}
                        className="ui-btn-secondary !py-2 !text-xs"
                      >
                        Details
                      </Link>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <EmptyResult onReset={resetFilters} hasFilters={hasFilters} />
        )
      ) : null}

      {/* ------------------------------------------------------ businesses -- */}
      {tab === "businesses" ? (
        businesses.length ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {businesses.map((business) => (
              <article
                key={business.id}
                className="flex h-full flex-col rounded-card border border-line bg-white p-5 shadow-card transition hover:-translate-y-0.5 hover:shadow-lift"
              >
                <div className="flex items-start gap-3">
                  <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand">
                    <Store size={22} />
                  </span>
                  <div className="min-w-0">
                    <h2 className="truncate text-base font-bold text-ink">{business.name}</h2>
                    <div className="mt-0.5 truncate text-xs font-semibold text-muted">
                      {categoryNameById[business.businessCategoryId] || "Business"}
                    </div>
                  </div>
                </div>

                <p className="mt-3 line-clamp-3 min-h-[3.75rem] text-sm leading-6 text-muted">
                  {business.description || "This business has not added a description yet."}
                </p>

                <div className="mt-3 flex flex-wrap gap-1.5">
                  {business.address?.city ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-surface px-2.5 py-1 text-[11px] font-semibold capitalize text-muted">
                      <MapPin size={11} /> {business.address.city}
                    </span>
                  ) : null}
                  {business.websiteStatus === "published" ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-green-50 px-2.5 py-1 text-[11px] font-bold text-green-600">
                      <Check size={11} /> Website live
                    </span>
                  ) : null}
                </div>

                {/* Equal button placement across every card, regardless of text length. */}
                <div className="mt-auto grid gap-2 pt-5">
                  <Link to={`/businesses/${business.slug}`} className="ui-btn-primary !py-2.5 !text-xs">
                    <ExternalLink size={14} /> View website
                  </Link>
                  <div className="grid grid-cols-2 gap-2">
                    <Link to={`/customer/businesses/${business.slug}`} className="ui-btn-secondary !py-2 !text-xs">
                      <Package size={13} /> Products
                    </Link>
                    {business.enabledModuleCodes?.includes("ai_chat") ? (
                      <Link to={`/customer/businesses/${business.slug}/chat`} className="ui-btn-secondary !py-2 !text-xs">
                        <Bot size={13} /> Ask AI
                      </Link>
                    ) : (
                      <WhatsAppAgentCta agent={business.whatsappAgent} compact />
                    )}
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyResult onReset={resetFilters} hasFilters={hasFilters} label="businesses" />
        )
      ) : null}
    </section>
  );
}

function EmptyResult({ onReset, hasFilters, label = "products" }) {
  return (
    <div className="flex flex-col items-center rounded-card border border-dashed border-line bg-surface px-6 py-14 text-center">
      <span className="grid h-14 w-14 place-items-center rounded-full bg-brand-50 text-brand">
        <ShoppingBag size={26} />
      </span>
      <h3 className="mt-4 text-lg font-bold text-ink">No {label} found</h3>
      <p className="mt-1.5 max-w-sm text-sm leading-6 text-muted">
        {hasFilters
          ? "Nothing matches those filters yet. Try a different category or clear the filters to see everything."
          : `There are no ${label} available right now. Please check back soon.`}
      </p>
      {hasFilters ? (
        <button type="button" onClick={onReset} className="ui-btn-primary mt-5">
          Clear filters
          <ArrowRight size={15} />
        </button>
      ) : null}
    </div>
  );
}
