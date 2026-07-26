import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { DynamicTable } from "../../components/dynamic/DynamicTable.jsx";
import { useModules } from "../../context/ModuleContext.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import { getCustomFields } from "../../services/customFieldApi.js";
import { getItem, resolveUploadUrl, uploadItemImage } from "../../services/itemApi.js";

export function ItemDetailPage() {
  const { itemId } = useParams();
  const { selectedTenant } = useTenant();
  const { hasModule, isLoadingModules } = useModules();
  const itemsModuleEnabled = hasModule("items");
  const [item, setItem] = useState(null);
  const [fields, setFields] = useState([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    loadItem();
  }, [selectedTenant?.id, itemId, itemsModuleEnabled]);

  async function loadItem() {
    if (!selectedTenant?.id || !itemId || !itemsModuleEnabled) return;
    setIsLoading(true);
    setError("");
    try {
      const [itemData, fieldData] = await Promise.all([
        getItem(selectedTenant.id, itemId),
        getCustomFields(selectedTenant.id, { moduleCode: "items", entityType: "item" }),
      ]);
      setItem(itemData);
      setFields(fieldData.filter((field) => field.isActive));
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to load item.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleImageUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setError("");
    setMessage("");
    try {
      const updated = await uploadItemImage(selectedTenant.id, item.id, file);
      setItem(updated);
      setMessage("Image uploaded.");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to upload image.");
    }
  }

  if (!selectedTenant || isLoadingModules || isLoading) {
    return (
      <section className="space-y-4">
        <h1 className="text-3xl font-semibold text-ink">Item Detail</h1>
        <p className="text-sm text-muted">Loading item details...</p>
      </section>
    );
  }

  if (!itemsModuleEnabled) {
    return (
      <section className="space-y-4">
        <h1 className="text-3xl font-semibold text-ink">Item Detail</h1>
        <p className="text-sm text-muted">Enable the Items module before viewing item records.</p>
      </section>
    );
  }

  if (error && !item) {
    return (
      <section className="space-y-4">
        <Link className="text-sm font-semibold text-brand" to="/dashboard/items">Back to items</Link>
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-3 border-b border-line pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <Link className="text-sm font-semibold text-brand" to="/dashboard/items">Back to items</Link>
          <p className="mt-4 text-sm font-semibold uppercase tracking-wide text-brand">Item Detail</p>
          <h1 className="mt-2 text-3xl font-semibold text-ink">{item.name}</h1>
          <p className="mt-2 text-sm capitalize text-muted">{item.itemType?.replace("_", " ")} / {item.status}</p>
        </div>
        <label className="inline-flex cursor-pointer rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white">
          Upload Image
          <input className="hidden" accept="image/*" type="file" onChange={handleImageUpload} />
        </label>
      </div>

      {message ? <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{message}</div> : null}
      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        <div className="space-y-5">
          <Card title="Pricing">
            <InfoRow label="Price" value={`${item.currency} ${item.price}`} />
            <InfoRow label="Cost price" value={`${item.currency} ${item.costPrice}`} />
            <InfoRow label="Unit" value={item.unit} />
            <InfoRow label="SKU" value={item.sku || "-"} />
          </Card>
          <Card title="Stock">
            <InfoRow label="Tracked" value={item.isStockTracked ? "Yes" : "No"} />
            <InfoRow label="Quantity" value={item.stock?.quantity ?? 0} />
            <InfoRow label="Low-stock threshold" value={item.stock?.lowStockThreshold ?? 0} />
            <InfoRow label="Reserved" value={item.stock?.reservedQuantity ?? 0} />
          </Card>
          <Card title="Flags">
            <InfoRow label="Sellable" value={item.isSellable ? "Yes" : "No"} />
            <InfoRow label="Bookable" value={item.isBookable ? "Yes" : "No"} />
          </Card>
          {item.serviceDetails?.durationMinutes ? (
            <Card title="Service Details">
              <InfoRow label="Duration" value={`${item.serviceDetails.durationMinutes} minutes`} />
              <InfoRow label="Buffer" value={`${item.serviceDetails.bufferMinutes || 0} minutes`} />
              <InfoRow label="Delivery mode" value={item.serviceDetails.deliveryMode?.replaceAll("_", " ") || "-"} />
            </Card>
          ) : null}
        </div>

        <div className="space-y-5">
          <Card title="Description">
            <p className="text-sm leading-6 text-muted">{item.description || "No description added."}</p>
          </Card>
          <Card title="Images">
            {item.images?.length ? (
              <div className="grid gap-3 sm:grid-cols-3">
                {item.images.map((image) => (
                  <img key={image.fileId} alt="" className="h-32 w-full rounded-md object-cover" src={resolveUploadUrl(image.url)} />
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted">No images uploaded.</p>
            )}
          </Card>
          <Card title="Custom Fields">
            <DynamicTable fields={fields} rows={[item.customFields || {}]} />
          </Card>
          {item.variants?.length ? (
            <Card title="Variants">
              <div className="space-y-3">
                {item.variants.map((variant) => (
                  <div key={`${variant.name}-${variant.sku}`} className="rounded-md border border-line px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="font-semibold text-ink">{variant.name}</div>
                        <div className="text-sm text-muted">{variant.sku || "-"}</div>
                      </div>
                      <div className="text-right text-sm text-muted">
                        <div>{item.currency} {variant.price}</div>
                        <div>{variant.stockQuantity} stock</div>
                      </div>
                    </div>
                    {Object.keys(variant.optionValues || {}).length ? (
                      <div className="mt-2 text-sm text-muted">
                        {Object.entries(variant.optionValues).map(([key, value]) => `${key}: ${value}`).join(" / ")}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            </Card>
          ) : null}
          {item.bundleComponents?.length ? (
            <Card title="Bundle Components">
              <div className="space-y-3">
                {item.bundleComponents.map((component, index) => (
                  <div key={`${component.itemId}-${index}`} className="rounded-md border border-line px-4 py-3 text-sm text-muted">
                    <div className="font-semibold text-ink">{component.itemName || component.itemId}</div>
                    <div className="capitalize">{component.itemType?.replaceAll("_", " ") || "-"}</div>
                    <div>Quantity: {component.quantity}</div>
                    <div>Optional: {component.isOptional ? "Yes" : "No"}</div>
                    <div>{component.notes || "-"}</div>
                  </div>
                ))}
              </div>
            </Card>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function Card({ title, children }) {
  return (
    <div className="rounded-md border border-line bg-white p-5 shadow-sm">
      <h2 className="mb-4 text-lg font-semibold text-ink">{title}</h2>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function InfoRow({ label, value }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line pb-3 last:border-b-0 last:pb-0">
      <span className="text-sm text-muted">{label}</span>
      <span className="text-right text-sm font-semibold text-ink">{value}</span>
    </div>
  );
}
