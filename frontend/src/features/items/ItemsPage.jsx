import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { DynamicForm } from "../../components/dynamic/DynamicForm.jsx";
import { DynamicTable } from "../../components/dynamic/DynamicTable.jsx";
import { useModules } from "../../context/ModuleContext.jsx";
import { useTenant } from "../../context/TenantContext.jsx";
import { getCustomFields } from "../../services/customFieldApi.js";
import {
  createItem,
  createItemCategory,
  deleteItem,
  deleteItemCategory,
  getItem,
  getItemCategories,
  getItems,
  resolveUploadUrl,
  updateItem,
  uploadItemImage,
} from "../../services/itemApi.js";

const emptyItemForm = {
  itemType: "product",
  name: "",
  description: "",
  categoryId: "",
  sku: "",
  price: "0",
  costPrice: "0",
  currency: "PKR",
  unit: "piece",
  status: "active",
  isSellable: true,
  isBookable: false,
  isStockTracked: true,
  quantity: "0",
  lowStockThreshold: "0",
  tagsText: "",
  serviceDurationMinutes: "0",
  serviceBufferMinutes: "0",
  serviceDeliveryMode: "onsite",
};

const emptyVariant = {
  name: "",
  sku: "",
  price: "0",
  compareAtPrice: "",
  stockQuantity: "0",
  lowStockThreshold: "0",
  isDefault: false,
  isActive: true,
  optionValuesText: "",
};

const emptyBundleComponent = {
  itemId: "",
  quantity: "1",
  isOptional: false,
  notes: "",
};

export function ItemsPage() {
  const { selectedTenant } = useTenant();
  const { hasModule, isLoadingModules } = useModules();
  const itemsModuleEnabled = hasModule("items");
  const [items, setItems] = useState([]);
  const [categories, setCategories] = useState([]);
  const [fields, setFields] = useState([]);
  const [meta, setMeta] = useState({});
  const [form, setForm] = useState(emptyItemForm);
  const [categoryForm, setCategoryForm] = useState({ name: "", description: "" });
  const [variants, setVariants] = useState([{ ...emptyVariant, isDefault: true }]);
  const [bundleComponents, setBundleComponents] = useState([{ ...emptyBundleComponent }]);
  const [customValues, setCustomValues] = useState({});
  const [customErrors, setCustomErrors] = useState([]);
  const [editingItem, setEditingItem] = useState(null);
  const [imageFile, setImageFile] = useState(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [serverMessage, setServerMessage] = useState("");
  const [serverError, setServerError] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (selectedTenant?.id && itemsModuleEnabled) {
      refreshItems();
      refreshCategories();
      getCustomFields(selectedTenant.id, { moduleCode: "items", entityType: "item" })
        .then((data) => setFields(data.filter((field) => field.isActive)))
        .catch(() => setFields([]));
    }
  }, [selectedTenant?.id, itemsModuleEnabled, statusFilter, typeFilter, categoryFilter]);

  async function refreshItems(nextSearch = search) {
    const result = await getItems(selectedTenant.id, {
      search: nextSearch,
      status: statusFilter || undefined,
      itemType: typeFilter || undefined,
      categoryId: categoryFilter || undefined,
      page: 1,
      limit: 20,
    });
    setItems(result.items);
    setMeta(result.meta);
  }

  async function refreshCategories() {
    const data = await getItemCategories(selectedTenant.id);
    setCategories(data);
  }

  function updateForm(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function resetForm() {
    setForm(emptyItemForm);
    setVariants([{ ...emptyVariant, isDefault: true }]);
    setBundleComponents([{ ...emptyBundleComponent }]);
    setCustomValues({});
    setCustomErrors([]);
    setEditingItem(null);
    setImageFile(null);
  }

  async function editItem(item) {
    const fullItem = await getItem(selectedTenant.id, item.id);
    setEditingItem(fullItem);
    setForm({
      itemType: fullItem.itemType || "product",
      name: fullItem.name || "",
      description: fullItem.description || "",
      categoryId: fullItem.categoryId || "",
      sku: fullItem.sku || "",
      price: String(fullItem.price ?? 0),
      costPrice: String(fullItem.costPrice ?? 0),
      currency: fullItem.currency || "PKR",
      unit: fullItem.unit || "piece",
      status: fullItem.status || "active",
      isSellable: Boolean(fullItem.isSellable),
      isBookable: Boolean(fullItem.isBookable),
      isStockTracked: Boolean(fullItem.isStockTracked),
      quantity: String(fullItem.stock?.quantity ?? 0),
      lowStockThreshold: String(fullItem.stock?.lowStockThreshold ?? 0),
      tagsText: (fullItem.tags || []).join(", "),
      serviceDurationMinutes: String(fullItem.serviceDetails?.durationMinutes ?? 0),
      serviceBufferMinutes: String(fullItem.serviceDetails?.bufferMinutes ?? 0),
      serviceDeliveryMode: fullItem.serviceDetails?.deliveryMode || "onsite",
    });
    setVariants(
      fullItem.variants?.length
        ? fullItem.variants.map((variant) => ({
            name: variant.name || "",
            sku: variant.sku || "",
            price: String(variant.price ?? 0),
            compareAtPrice: variant.compareAtPrice ?? "",
            stockQuantity: String(variant.stockQuantity ?? 0),
            lowStockThreshold: String(variant.lowStockThreshold ?? 0),
            isDefault: Boolean(variant.isDefault),
            isActive: Boolean(variant.isActive ?? true),
            optionValuesText: Object.entries(variant.optionValues || {}).map(([key, value]) => `${key}:${value}`).join(", "),
          }))
        : [{ ...emptyVariant, isDefault: true }],
    );
    setBundleComponents(
      fullItem.bundleComponents?.length
        ? fullItem.bundleComponents.map((component) => ({
            itemId: component.itemId || "",
            quantity: String(component.quantity ?? 1),
            isOptional: Boolean(component.isOptional),
            notes: component.notes || "",
          }))
        : [{ ...emptyBundleComponent }],
    );
    setCustomValues(fullItem.customFields || {});
    setCustomErrors([]);
    setImageFile(null);
  }

  function addVariant() {
    setVariants((current) => [...current, { ...emptyVariant }]);
  }

  function updateVariant(index, key, value) {
    setVariants((current) =>
      current.map((variant, currentIndex) => {
        if (currentIndex !== index) return variant;
        if (key === "isDefault" && value) {
          return { ...variant, isDefault: true };
        }
        return { ...variant, [key]: value };
      }).map((variant, currentIndex) => (key === "isDefault" && value && currentIndex !== index ? { ...variant, isDefault: false } : variant)),
    );
  }

  function removeVariant(index) {
    setVariants((current) => {
      const next = current.filter((_, currentIndex) => currentIndex !== index);
      if (!next.length) return [{ ...emptyVariant, isDefault: true }];
      if (!next.some((variant) => variant.isDefault)) next[0].isDefault = true;
      return [...next];
    });
  }

  function addBundleComponent() {
    setBundleComponents((current) => [...current, { ...emptyBundleComponent }]);
  }

  function updateBundleComponent(index, key, value) {
    setBundleComponents((current) => current.map((component, currentIndex) => (currentIndex === index ? { ...component, [key]: value } : component)));
  }

  function removeBundleComponent(index) {
    setBundleComponents((current) => {
      const next = current.filter((_, currentIndex) => currentIndex !== index);
      return next.length ? next : [{ ...emptyBundleComponent }];
    });
  }

  function parseOptionValues(text) {
    return text
      .split(",")
      .map((chunk) => chunk.trim())
      .filter(Boolean)
      .reduce((accumulator, chunk) => {
        const [key, ...rest] = chunk.split(":");
        if (key && rest.length) accumulator[key.trim()] = rest.join(":").trim();
        return accumulator;
      }, {});
  }

  async function submitItem(event) {
    event.preventDefault();
    setServerError("");
    setServerMessage("");
    setCustomErrors([]);
    setIsSaving(true);

    const payload = {
      itemType: form.itemType,
      name: form.name,
      description: form.description,
      categoryId: form.categoryId || null,
      sku: form.sku,
      price: Number(form.price || 0),
      costPrice: Number(form.costPrice || 0),
      currency: form.currency,
      unit: form.unit,
      status: form.status,
      isSellable: form.isSellable,
      isBookable: form.isBookable,
      isStockTracked: form.isStockTracked,
      stock: {
        quantity: Number(form.quantity || 0),
        lowStockThreshold: Number(form.lowStockThreshold || 0),
        reservedQuantity: editingItem?.stock?.reservedQuantity || 0,
      },
      serviceDetails: {
        durationMinutes: Number(form.serviceDurationMinutes || 0),
        bufferMinutes: Number(form.serviceBufferMinutes || 0),
        deliveryMode: form.serviceDeliveryMode,
      },
      variants:
        variants
          .filter((variant) => variant.name.trim())
          .map((variant) => ({
            name: variant.name.trim(),
            sku: variant.sku.trim(),
            price: Number(variant.price || 0),
            compareAtPrice: variant.compareAtPrice === "" ? null : Number(variant.compareAtPrice),
            stockQuantity: Number(variant.stockQuantity || 0),
            lowStockThreshold: Number(variant.lowStockThreshold || 0),
            isDefault: Boolean(variant.isDefault),
            isActive: Boolean(variant.isActive),
            optionValues: parseOptionValues(variant.optionValuesText),
          })),
      bundleComponents:
        bundleComponents
          .filter((component) => component.itemId)
          .map((component) => ({
            itemId: component.itemId,
            quantity: Number(component.quantity || 1),
            isOptional: Boolean(component.isOptional),
            notes: component.notes,
          })),
      tags: form.tagsText.split(",").map((tag) => tag.trim()).filter(Boolean),
      customFields: customValues,
    };

    try {
      const saved = editingItem
        ? await updateItem(selectedTenant.id, editingItem.id, payload)
        : await createItem(selectedTenant.id, payload);
      if (imageFile) {
        await uploadItemImage(selectedTenant.id, saved.id, imageFile);
      }
      setServerMessage(editingItem ? "Item updated." : "Item created.");
      resetForm();
      await refreshItems();
    } catch (error) {
      const detail = error.response?.data?.detail;
      if (Array.isArray(detail)) {
        setCustomErrors(detail);
        setServerError("Please fix custom field validation errors.");
      } else {
        setServerError(detail || "Unable to save item.");
      }
    } finally {
      setIsSaving(false);
    }
  }

  async function submitCategory(event) {
    event.preventDefault();
    setServerError("");
    setServerMessage("");
    try {
      await createItemCategory(selectedTenant.id, categoryForm);
      setCategoryForm({ name: "", description: "" });
      setServerMessage("Category created.");
      await refreshCategories();
    } catch (error) {
      setServerError(error.response?.data?.detail || "Unable to save category.");
    }
  }

  async function archiveItem(itemId) {
    await deleteItem(selectedTenant.id, itemId);
    await refreshItems();
  }

  async function disableCategory(categoryId) {
    await deleteItemCategory(selectedTenant.id, categoryId);
    await refreshCategories();
  }

  const selectableBundleItems = useMemo(
    () => items.filter((item) => !editingItem || item.id !== editingItem.id),
    [items, editingItem],
  );
  const tableRows = useMemo(() => items.map((item) => item.customFields || {}), [items]);

  if (!selectedTenant) {
    return (
      <section className="space-y-4">
        <h1 className="text-3xl font-semibold text-ink">Items</h1>
        <p className="text-sm text-muted">Create a business before adding items.</p>
        <Link className="inline-flex rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white" to="/dashboard/business">
          Create Business
        </Link>
      </section>
    );
  }

  if (isLoadingModules) {
    return (
      <section className="space-y-4">
        <h1 className="text-3xl font-semibold text-ink">Items</h1>
        <p className="text-sm text-muted">Loading item module settings...</p>
      </section>
    );
  }

  if (!itemsModuleEnabled) {
    return (
      <section className="space-y-4">
        <h1 className="text-3xl font-semibold text-ink">Items</h1>
        <p className="text-sm text-muted">Enable the Items module before managing products and services.</p>
        <Link className="inline-flex rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white" to="/dashboard/modules">
          Enable Module
        </Link>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-3 border-b border-line pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-brand">Catalog Engine</p>
          <h1 className="mt-2 text-3xl font-semibold text-ink">Items and Services</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
            Manage products, services, packages, variants, durations, bundles, stock, images, and tenant-specific catalog fields.
          </p>
        </div>
        <Link className="inline-flex rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white" to="/dashboard/items/import">
          Import Excel
        </Link>
      </div>

      {serverMessage ? <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">{serverMessage}</div> : null}
      {serverError ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{serverError}</div> : null}

      <div className="grid gap-6 xl:grid-cols-[470px_1fr]">
        <div className="space-y-5">
          <form className="space-y-4 rounded-md border border-line bg-white p-5 shadow-sm" onSubmit={submitItem}>
            <h2 className="text-lg font-semibold text-ink">{editingItem ? "Edit Item" : "Add Item"}</h2>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Type">
                <select className="form-input" value={form.itemType} onChange={(event) => updateForm("itemType", event.target.value)}>
                  <option value="product">Product</option>
                  <option value="service">Service</option>
                  <option value="package">Package</option>
                  <option value="raw_material">Raw material</option>
                  <option value="asset">Asset</option>
                  <option value="digital_product">Digital product</option>
                </select>
              </Field>
              <Field label="Status">
                <select className="form-input" value={form.status} onChange={(event) => updateForm("status", event.target.value)}>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                  <option value="archived">Archived</option>
                </select>
              </Field>
            </div>
            <Field label="Name">
              <input className="form-input" required value={form.name} onChange={(event) => updateForm("name", event.target.value)} />
            </Field>
            <Field label="Description">
              <textarea className="form-input min-h-24" value={form.description} onChange={(event) => updateForm("description", event.target.value)} />
            </Field>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Category">
                <select className="form-input" value={form.categoryId} onChange={(event) => updateForm("categoryId", event.target.value)}>
                  <option value="">No category</option>
                  {categories.filter((category) => category.isActive).map((category) => (
                    <option key={category.id} value={category.id}>{category.name}</option>
                  ))}
                </select>
                {!categories.filter((category) => category.isActive).length ? (
                  <div className="mt-1 text-xs text-amber-700">No categories yet. Create one below or import Excel with a category column; Phase 32 auto-creates categories from Excel.</div>
                ) : null}
              </Field>
              <Field label="SKU">
                <input className="form-input" value={form.sku} onChange={(event) => updateForm("sku", event.target.value)} />
              </Field>
              <Field label="Base price">
                <input className="form-input" min="0" step="0.01" type="number" value={form.price} onChange={(event) => updateForm("price", event.target.value)} />
              </Field>
              <Field label="Cost price">
                <input className="form-input" min="0" step="0.01" type="number" value={form.costPrice} onChange={(event) => updateForm("costPrice", event.target.value)} />
              </Field>
              <Field label="Currency">
                <input className="form-input" value={form.currency} onChange={(event) => updateForm("currency", event.target.value)} />
              </Field>
              <Field label="Unit">
                <select className="form-input" value={form.unit} onChange={(event) => updateForm("unit", event.target.value)}>
                  <option value="piece">Piece</option>
                  <option value="hour">Hour</option>
                  <option value="session">Session</option>
                  <option value="kg">Kg</option>
                  <option value="liter">Liter</option>
                  <option value="month">Month</option>
                  <option value="custom">Custom</option>
                </select>
              </Field>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <Toggle label="Sellable" checked={form.isSellable} onChange={(value) => updateForm("isSellable", value)} />
              <Toggle label="Bookable" checked={form.isBookable} onChange={(value) => updateForm("isBookable", value)} />
              <Toggle label="Track stock" checked={form.isStockTracked} onChange={(value) => updateForm("isStockTracked", value)} />
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Stock quantity">
                <input className="form-input" min="0" step="0.01" type="number" value={form.quantity} onChange={(event) => updateForm("quantity", event.target.value)} />
              </Field>
              <Field label="Low-stock threshold">
                <input className="form-input" min="0" step="0.01" type="number" value={form.lowStockThreshold} onChange={(event) => updateForm("lowStockThreshold", event.target.value)} />
              </Field>
            </div>

            {form.itemType === "service" || form.isBookable ? (
              <div className="rounded-md border border-line bg-surface p-4">
                <div className="text-sm font-semibold text-ink">Service Duration</div>
                <div className="mt-3 grid gap-4 md:grid-cols-3">
                  <Field label="Duration (minutes)">
                    <input className="form-input" min="0" type="number" value={form.serviceDurationMinutes} onChange={(event) => updateForm("serviceDurationMinutes", event.target.value)} />
                  </Field>
                  <Field label="Buffer (minutes)">
                    <input className="form-input" min="0" type="number" value={form.serviceBufferMinutes} onChange={(event) => updateForm("serviceBufferMinutes", event.target.value)} />
                  </Field>
                  <Field label="Delivery mode">
                    <select className="form-input" value={form.serviceDeliveryMode} onChange={(event) => updateForm("serviceDeliveryMode", event.target.value)}>
                      <option value="onsite">Onsite</option>
                      <option value="remote">Remote</option>
                      <option value="pickup">Pickup</option>
                      <option value="home_visit">Home visit</option>
                      <option value="hybrid">Hybrid</option>
                    </select>
                  </Field>
                </div>
              </div>
            ) : null}

            <div className="rounded-md border border-line bg-surface p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-ink">Variants and Options</div>
                  <div className="text-xs text-muted">Use `Size:Large, Color:Black` format for option values.</div>
                </div>
                <button type="button" className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink hover:bg-white" onClick={addVariant}>
                  Add Variant
                </button>
              </div>
              <div className="mt-4 space-y-4">
                {variants.map((variant, index) => (
                  <div key={index} className="rounded-md border border-line bg-white p-4">
                    <div className="grid gap-4 md:grid-cols-2">
                      <Field label="Variant name">
                        <input className="form-input" value={variant.name} onChange={(event) => updateVariant(index, "name", event.target.value)} />
                      </Field>
                      <Field label="Variant SKU">
                        <input className="form-input" value={variant.sku} onChange={(event) => updateVariant(index, "sku", event.target.value)} />
                      </Field>
                      <Field label="Variant price">
                        <input className="form-input" min="0" step="0.01" type="number" value={variant.price} onChange={(event) => updateVariant(index, "price", event.target.value)} />
                      </Field>
                      <Field label="Compare-at price">
                        <input className="form-input" min="0" step="0.01" type="number" value={variant.compareAtPrice} onChange={(event) => updateVariant(index, "compareAtPrice", event.target.value)} />
                      </Field>
                      <Field label="Stock quantity">
                        <input className="form-input" min="0" step="0.01" type="number" value={variant.stockQuantity} onChange={(event) => updateVariant(index, "stockQuantity", event.target.value)} />
                      </Field>
                      <Field label="Low-stock threshold">
                        <input className="form-input" min="0" step="0.01" type="number" value={variant.lowStockThreshold} onChange={(event) => updateVariant(index, "lowStockThreshold", event.target.value)} />
                      </Field>
                    </div>
                    <Field label="Option values">
                      <input className="form-input" placeholder="Size:Large, Color:Black" value={variant.optionValuesText} onChange={(event) => updateVariant(index, "optionValuesText", event.target.value)} />
                    </Field>
                    <div className="mt-3 flex gap-3">
                      <Toggle label="Default" checked={variant.isDefault} onChange={(value) => updateVariant(index, "isDefault", value)} />
                      <Toggle label="Active" checked={variant.isActive} onChange={(value) => updateVariant(index, "isActive", value)} />
                      <button type="button" className="rounded-md border border-line px-3 py-2 text-sm font-semibold text-ink hover:bg-surface" onClick={() => removeVariant(index)}>
                        Remove
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {form.itemType === "package" ? (
              <div className="rounded-md border border-line bg-surface p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-ink">Bundle Components</div>
                    <div className="text-xs text-muted">Compose this package from existing products or services.</div>
                  </div>
                  <button type="button" className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink hover:bg-white" onClick={addBundleComponent}>
                    Add Component
                  </button>
                </div>
                <div className="mt-4 space-y-4">
                  {bundleComponents.map((component, index) => (
                    <div key={index} className="rounded-md border border-line bg-white p-4">
                      <div className="grid gap-4 md:grid-cols-2">
                        <Field label="Bundle item">
                          <select className="form-input" value={component.itemId} onChange={(event) => updateBundleComponent(index, "itemId", event.target.value)}>
                            <option value="">Select item</option>
                            {selectableBundleItems.map((item) => (
                              <option key={item.id} value={item.id}>{item.name}</option>
                            ))}
                          </select>
                        </Field>
                        <Field label="Quantity">
                          <input className="form-input" min="0.01" step="0.01" type="number" value={component.quantity} onChange={(event) => updateBundleComponent(index, "quantity", event.target.value)} />
                        </Field>
                      </div>
                      <Field label="Notes">
                        <input className="form-input" value={component.notes} onChange={(event) => updateBundleComponent(index, "notes", event.target.value)} />
                      </Field>
                      <div className="mt-3 flex gap-3">
                        <Toggle label="Optional" checked={component.isOptional} onChange={(value) => updateBundleComponent(index, "isOptional", value)} />
                        <button type="button" className="rounded-md border border-line px-3 py-2 text-sm font-semibold text-ink hover:bg-surface" onClick={() => removeBundleComponent(index)}>
                          Remove
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            <Field label="Tags">
              <input className="form-input" placeholder="featured, seasonal" value={form.tagsText} onChange={(event) => updateForm("tagsText", event.target.value)} />
            </Field>
            <Field label="Image">
              <input className="form-input" accept="image/*" type="file" onChange={(event) => setImageFile(event.target.files?.[0] || null)} />
              <div className="mt-1 text-xs text-muted">
                {imageFile ? `Selected image: ${imageFile.name}` : "Upload an image while creating/editing this product. Excel import also supports an optional imageUrl column."}
              </div>
            </Field>
            <div className="border-t border-line pt-4">
              <h3 className="mb-3 text-sm font-semibold text-ink">Custom fields</h3>
              <DynamicForm fields={fields} values={customValues} onChange={setCustomValues} errors={customErrors} />
            </div>
            <div className="flex gap-2">
              <button className="flex-1 rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700" disabled={isSaving}>
                {isSaving ? "Saving..." : editingItem ? "Update Item" : "Create Item"}
              </button>
              {editingItem ? (
                <button type="button" className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink hover:bg-surface" onClick={resetForm}>
                  Cancel
                </button>
              ) : null}
            </div>
          </form>

          <form className="space-y-4 rounded-md border border-line bg-white p-5 shadow-sm" onSubmit={submitCategory}>
            <h2 className="text-lg font-semibold text-ink">Categories</h2>
            <p className="text-xs leading-5 text-muted">Create categories here before manual item entry. Excel imports now auto-create missing category names.</p>
            <Field label="Category name">
              <input className="form-input" required value={categoryForm.name} onChange={(event) => setCategoryForm((current) => ({ ...current, name: event.target.value }))} />
            </Field>
            <Field label="Description">
              <input className="form-input" value={categoryForm.description} onChange={(event) => setCategoryForm((current) => ({ ...current, description: event.target.value }))} />
            </Field>
            <button className="w-full rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white">Create Category</button>
            <div className="space-y-2">
              {categories.map((category) => (
                <div key={category.id} className="flex items-center justify-between rounded-md border border-line px-3 py-2 text-sm">
                  <div>
                    <div className="font-semibold text-ink">{category.name}</div>
                    <div className="text-xs text-muted">{category.isActive ? "Active" : "Disabled"}</div>
                  </div>
                  {category.isActive ? (
                    <button type="button" className="rounded-md border border-line px-2.5 py-1 text-xs font-semibold text-ink" onClick={() => disableCategory(category.id)}>
                      Disable
                    </button>
                  ) : null}
                </div>
              ))}
            </div>
          </form>
        </div>

        <div className="space-y-5">
          <div className="rounded-md border border-line bg-white p-5 shadow-sm">
            <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
              <div>
                <h2 className="text-lg font-semibold text-ink">Catalog Records</h2>
                <p className="mt-1 text-sm text-muted">{meta.total || 0} records found.</p>
              </div>
              <div className="grid gap-2 md:grid-cols-5">
                <input className="form-input md:col-span-2" placeholder="Search name, SKU, variant, tag" value={search} onChange={(event) => setSearch(event.target.value)} />
                <select className="form-input" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
                  <option value="">All types</option>
                  <option value="product">Product</option>
                  <option value="service">Service</option>
                  <option value="package">Package</option>
                  <option value="raw_material">Raw material</option>
                  <option value="asset">Asset</option>
                  <option value="digital_product">Digital</option>
                </select>
                <select className="form-input" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                  <option value="">All status</option>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                  <option value="archived">Archived</option>
                </select>
                <button type="button" className="rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white" onClick={() => refreshItems()}>
                  Search
                </button>
              </div>
            </div>
            <div className="mt-3">
              <select className="form-input max-w-xs" value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
                <option value="">All categories</option>
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>{category.name}</option>
                ))}
              </select>
            </div>

            <div className="mt-4 overflow-hidden rounded-md border border-line">
              <table className="min-w-full divide-y divide-line text-sm">
                <thead className="bg-surface">
                  <tr>
                    <th className="px-4 py-3 text-left font-semibold text-ink">Item</th>
                    <th className="px-4 py-3 text-left font-semibold text-ink">Type</th>
                    <th className="px-4 py-3 text-left font-semibold text-ink">Catalog</th>
                    <th className="px-4 py-3 text-left font-semibold text-ink">Status</th>
                    <th className="px-4 py-3 text-right font-semibold text-ink">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line bg-white">
                  {items.map((item) => (
                    <tr key={item.id}>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          {item.images?.[0]?.url ? (
                            <img alt="" className="h-10 w-10 rounded-md object-cover" src={resolveUploadUrl(item.images[0].url)} />
                          ) : (
                            <div className="h-10 w-10 rounded-md bg-surface" />
                          )}
                          <div>
                            <Link className="font-semibold text-ink hover:text-brand" to={`/dashboard/items/${item.id}`}>{item.name}</Link>
                            <div className="text-xs text-muted">{item.sku || "-"}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 capitalize text-muted">{item.itemType?.replace("_", " ")}</td>
                      <td className="px-4 py-3 text-muted">
                        <div>{item.currency} {item.price}</div>
                        {item.serviceDetails?.durationMinutes ? <div>{item.serviceDetails.durationMinutes} min service</div> : null}
                        {item.variants?.length ? <div>{item.variants.length} variants</div> : null}
                        {item.bundleComponents?.length ? <div>{item.bundleComponents.length} bundle items</div> : null}
                      </td>
                      <td className="px-4 py-3 capitalize text-muted">{item.status}</td>
                      <td className="px-4 py-3 text-right">
                        <Link className="mr-2 inline-flex rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink hover:bg-surface" to={`/dashboard/items/${item.id}`}>View</Link>
                        <button type="button" className="mr-2 rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink hover:bg-surface" onClick={() => editItem(item)}>Edit</button>
                        <button type="button" className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink hover:bg-surface" onClick={() => archiveItem(item.id)}>Archive</button>
                      </td>
                    </tr>
                  ))}
                  {!items.length ? (
                    <tr>
                      <td className="px-4 py-5 text-sm text-muted" colSpan="5">No items yet.</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-md border border-line bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-lg font-semibold text-ink">Custom Field Table View</h2>
            <DynamicTable fields={fields} rows={tableRows} />
          </div>
        </div>
      </div>
    </section>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-ink">{label}</span>
      {children}
    </label>
  );
}

function Toggle({ label, checked, onChange }) {
  return (
    <label className="flex h-[46px] items-center rounded-md border border-line px-3 text-sm font-medium text-ink">
      <input checked={checked} type="checkbox" onChange={(event) => onChange(event.target.checked)} />
      <span className="ml-2">{label}</span>
    </label>
  );
}
