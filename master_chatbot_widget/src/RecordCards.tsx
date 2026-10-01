import { useState } from "react";
import { Package, UserRound } from "lucide-react";
import type { MasterChatbotMessage } from "./types.js";

type RecordData = Record<string, unknown>;
type CardAction =
  | { type: "cancel"; order_id?: string; order_item_id?: string; product_id?: string }
  | { type: "return"; order_id?: string; order_item_id?: string; product_id?: string }
  | { type: "refund"; order_id?: string; order_item_id?: string; product_id?: string }
  | { type: "replacement"; order_id?: string; order_item_id?: string; product_id?: string };

const isRecord = (value: unknown): value is RecordData =>
  !!value && typeof value === "object" && !Array.isArray(value);
const label = (key: string) =>
  key.replace(/_/g, " ").replace(/([a-z])([A-Z])/g, "$1 $2").replace(/^./, c => c.toUpperCase());
const hidden = /password|token|secret|authorization|^user_id$|^id$|_id$|^slug$|_slug$/i;
const imageKey = /^(images?|image_url|photo_url|avatar|avatar_url|thumbnail|thumbnail_url|product_image|media)$/;
const text = (value: unknown): string =>
  typeof value === "boolean" ? (value ? "Yes" : "No")
  : typeof value === "string" || typeof value === "number" ? String(value)
  : "";

const hasFlag = (record: RecordData, ...keys: string[]) =>
  keys.some((key) => {
    const value = record[key];
    return value === true || value === "true" || value === 1 || value === "yes";
  });

const statusText = (record: RecordData): string =>
  text(record.status ?? record.delivery_status ?? record.order_status ?? record.fulfillment_status ?? record.lifecycle_status) || "";
const isDeliveredStatus = (record: RecordData) =>
  /delivered|delivery completed|fulfilled/i.test(statusText(record));
const canCancel = (record: RecordData) =>
  hasFlag(record, "can_cancel", "cancel_eligible", "is_cancelable") ||
  /pending|confirmed|processing|awaiting_shipment|paid/i.test(statusText(record));
const canReturn = (record: RecordData) =>
  hasFlag(record, "can_return", "return_eligible", "is_returnable") || /delivered/i.test(statusText(record));
const canRefund = (record: RecordData) =>
  hasFlag(record, "can_refund", "refund_eligible", "is_refundable");
const canReplace = (record: RecordData) =>
  hasFlag(record, "can_replace", "can_replacement", "replacement_eligible", "is_replaceable");
const normalizeId = (record: RecordData, keys: string[]) =>
  keys.map((key) => text(record[key])).find(Boolean) || "";

/** True when the record is an order (or order item) — shopping buttons must be hidden. */
const detectOrderCard = (record: RecordData): boolean =>
  Boolean(
    record.order_id ?? record.orderId ?? record.order_number ??
    record.order_status ?? record.delivery_status ?? record.fulfillment_status,
  );

/** True when the record is an address — must never render as a product/order card. */
const detectAddressCard = (record: RecordData): boolean =>
  Boolean(
    (record.recipient_name ?? record.line1 ?? record.postal_code ?? record.address_id) &&
    !(record.name ?? record.product_name ?? record.order_id ?? record.order_number),
  );

export function extractRecords(value: unknown, depth = 0): RecordData[] {
  if (depth > 6) return [];
  if (Array.isArray(value)) return value.flatMap(item => extractRecords(item, depth + 1));
  if (!isRecord(value)) return [];
  const identity = ["id", "name", "title", "first_name", "full_name", "patient_code"].some(
    key => value[key] != null,
  );
  if (!identity) {
    const nested = Object.entries(value).filter(
      ([key, item]) => !imageKey.test(key) && (Array.isArray(item) || isRecord(item)),
    );
    if (nested.length) return nested.flatMap(([, item]) => extractRecords(item, depth + 1));
  }
  return [value];
}

function safeImage(value: unknown): string | undefined {
  if (Array.isArray(value)) return value.map(safeImage).find(Boolean);
  if (isRecord(value)) return safeImage(value.url ?? value.image_url ?? value.media_url ?? value.src);
  if (typeof value !== "string") return undefined;
  return /^(https?:\/\/|\/(?!\/))/i.test(value) ? value : undefined;
}

function Details({ record, depth = 0 }: { record: RecordData; depth?: number }) {
  if (depth > 3) return null;
  return (
    <dl className="master-chatbot-record-fields">
      {Object.entries(record)
        .filter(([key, value]) => !hidden.test(key) && !imageKey.test(key) && value != null && value !== "")
        .map(([key, value]) => (
          <div key={key}>
            <dt>{label(key)}</dt>
            <dd>
              {isRecord(value) ? <Details record={value} depth={depth + 1} />
               : Array.isArray(value) ? value.map((item, i) => (
                   <div key={i}>{isRecord(item) ? <Details record={item} depth={depth + 1} /> : text(item)}</div>
                 ))
               : text(value)}
            </dd>
          </div>
        ))}
    </dl>
  );
}

function RecordCard({
  record, index, onSend, disabled, canAdd,
  selected, onToggleSelect, canSelect,
  flowAction, onAction,
}: {
  record: RecordData;
  index: number;
  onSend?: (message: string) => void;
  disabled?: boolean;
  canAdd: boolean;
  selected: boolean;
  onToggleSelect: () => void;
  canSelect: boolean;
  flowAction?: "cancel" | "return_refund";
  onAction?: (action: CardAction) => void;
}) {
  const [failedImage, setFailedImage] = useState(false);

  const person = record.first_name != null || record.patient_code != null || record.full_name != null;
  const title =
    text(record.name ?? record.product_name ?? record.full_name ?? record.title ?? record.order_number ?? record.recipient_name) ||
    [record.first_name, record.middle_name, record.last_name].map(text).filter(Boolean).join(" ") ||
    text(record.patient_code ?? record.code) ||
    `Record ${index + 1}`;
  const src = Object.entries(record)
    .filter(([key]) => imageKey.test(key))
    .map(([, value]) => safeImage(value))
    .find(Boolean);
  const subtitle = text(record.brand_name ?? record.category_name ?? record.patient_code ?? record.role ?? record.type);
  const variants = Array.isArray(record.variants) ? record.variants.filter(isRecord) : [];
  const variant = variants.find(item => item.is_default) ?? variants[0];
  const price = record.sale_price ?? record.price ?? record.unit_price ?? variant?.price;
  const currency = text(record.currency ?? record.currency_code ?? variant?.currency);
  let formattedPrice = text(price);
  if (price != null && currency && Number.isFinite(Number(price))) {
    try {
      formattedPrice = new Intl.NumberFormat(undefined, { style: "currency", currency }).format(Number(price));
    } catch {
      formattedPrice = `${currency} ${text(price)}`;
    }
  }

  const preview = Object.entries(record)
    .filter(([key, value]) =>
      !hidden.test(key) && !imageKey.test(key) &&
      !/^(name|full_name|title|first_name|middle_name|last_name|description|short_description|price|sale_price|unit_price|currency|currency_code|brand_name|category_name|patient_code)$/.test(key) &&
      value != null && value !== "" && typeof value !== "object")
    .slice(0, 3);

  const orderId   = normalizeId(record, ["order_id", "orderId", "id"]);
  const itemId    = normalizeId(record, ["order_item_id", "item_id", "id"]);
  const productId = normalizeId(record, ["product_id", "productId", "variant_id", "id"]);
  const deliveryStatus = text(record.delivery_status ?? record.fulfillment_status ?? record.order_status);

  const eligibleForCancel      = canCancel(record);
  const eligibleForReturn      = canReturn(record) || Boolean(record.can_return);
  const eligibleForRefund      = canRefund(record) || Boolean(record.can_refund);
  const eligibleForReplacement = canReplace(record) || Boolean(record.can_replace);

  const isProductCard = Boolean(
    record.name || record.product_name || record.slug || record.sku ||
    productId || variants.length || price != null,
  );
  // Order cards must not show shopping actions (Add to cart, Buy now, Select/compare)
  const isOrderCard = detectOrderCard(record);

  const fireAction = (action: CardAction) => {
    if (onAction) { onAction(action); return; }
    if (!onSend) return;
    if (action.type === "cancel") {
      onSend(`cancel order_id ${action.order_id ?? orderId}`);
      return;
    }
    if (action.type === "return") {
      onSend(`__return_refund_select__ item_id=${action.order_item_id ?? itemId} name=${encodeURIComponent(title)}`);
      return;
    }
    if (action.type === "refund") {
      onSend(`__return_refund_select__ item_id=${action.order_item_id ?? itemId} name=${encodeURIComponent(title)}`);
      return;
    }
    onSend(`find similar products for ${action.product_id ?? productId ?? title}`);
  };

  return (
    <article className={`master-chatbot-record-card${selected ? " is-selected" : ""}`}>
      <div className="master-chatbot-record-top">
        <div className={`master-chatbot-record-image${person ? " is-person" : ""}`}>
          {src && !failedImage
            ? <img src={src} alt={title} loading="lazy" onError={() => setFailedImage(true)} />
            : person ? <UserRound size={28} /> : <Package size={28} />}
        </div>
        <div className="master-chatbot-record-heading">
          {subtitle && <span className="master-chatbot-record-subtitle">{subtitle}</span>}
          <strong>{title}</strong>
          {price != null && <div className="master-chatbot-record-price">{formattedPrice}</div>}
          {record.status != null && <span className="master-chatbot-record-status">{text(record.status)}</span>}
        </div>
      </div>

      {record.short_description != null && (
        <p className="master-chatbot-record-description">{text(record.short_description)}</p>
      )}

      <dl className="master-chatbot-record-fields">
        {preview.map(([key, value]) => (
          <div key={key}><dt>{label(key)}</dt><dd>{text(value)}</dd></div>
        ))}
      </dl>

      {/* Shopping actions — hidden when card comes from an order */}
      {isProductCard && !isOrderCard && (
        <div className="master-chatbot-card-actions">
          {canAdd && onSend && (
            <button
              type="button"
              disabled={disabled}
              onClick={() => onSend(`Add quantity 1 of product_id ${text(record.id ?? productId)} to my cart`)}
            >
              Add to cart
            </button>
          )}
          <button
            type="button"
            disabled={disabled}
            className="master-chatbot-card-buy"
            data-action-type="checkout"
            data-product-id={productId || text(record.id)}
            onClick={() => {
              if (onSend) {
                onSend(`Proceed to checkout for product_id ${text(record.id ?? productId)} (${title})`);
              }
            }}
          >
            Buy now
          </button>
          {canSelect && (
            <button
              type="button"
              disabled={disabled}
              aria-pressed={selected}
              className={selected ? "master-chatbot-action-selected" : undefined}
              onClick={onToggleSelect}
            >
              {selected ? "Selected ✓" : "Select"}
            </button>
          )}
        </div>
      )}

      {/* Cancel order action */}
      {(flowAction === "cancel" || eligibleForCancel) && orderId && (
        <div className="master-chatbot-card-actions">
          <button
            type="button"
            disabled={disabled}
            className="master-chatbot-action-danger"
            data-action-type="cancel"
            data-order-id={orderId}
            data-order-item-id={itemId || ""}
            data-product-id={productId || ""}
            onClick={() => fireAction({
              type: "cancel",
              order_id: orderId,
              order_item_id: itemId || undefined,
              product_id: productId || undefined,
            })}
          >
            {flowAction === "cancel" ? "Cancel this order" : "Cancel Order"}
          </button>
        </div>
      )}

      {/* Delivered product actions */}
      {(isDeliveredStatus(record) || deliveryStatus) && (
        <div className="master-chatbot-card-actions">
          {eligibleForReturn && (
            <button
              type="button" disabled={disabled}
              data-action-type="return"
              onClick={() => fireAction({ type: "return", order_id: orderId || undefined, order_item_id: itemId || undefined, product_id: productId || undefined })}
            >Return</button>
          )}
          {eligibleForRefund && (
            <button
              type="button" disabled={disabled}
              data-action-type="refund"
              onClick={() => fireAction({ type: "refund", order_id: orderId || undefined, order_item_id: itemId || undefined, product_id: productId || undefined })}
            >Refund</button>
          )}
          {eligibleForReplacement && (
            <button
              type="button" disabled={disabled}
              data-action-type="replacement"
              onClick={() => fireAction({ type: "replacement", order_id: orderId || undefined, order_item_id: itemId || undefined, product_id: productId || undefined })}
            >Replacement</button>
          )}
        </div>
      )}

      {/* Return / refund item selection */}
      {flowAction === "return_refund" && itemId && onSend && (
        <div className="master-chatbot-card-actions">
          <button
            type="button"
            disabled={disabled}
            onClick={() => onSend(`__return_refund_select__ item_id=${itemId} name=${encodeURIComponent(title)}`)}
          >
            Select this item
          </button>
        </div>
      )}

      <details className="master-chatbot-record-details">
        <summary>View details<span aria-hidden="true"> +</span></summary>
        <Details record={record} />
      </details>
    </article>
  );
}

function ComparisonTable({ records }: { records: RecordData[] }) {
  const fields = ["price", "brand_name", "category_name", "average_rating", "short_description"];
  return (
    <div className="master-chatbot-comparison" tabIndex={0} role="region" aria-label="Product comparison">
      <table>
        <caption>Product comparison</caption>
        <thead>
          <tr>
            <th>Details</th>
            {records.map((record, i) => (
              <th key={i}>{text(record.name ?? record.product_name) || `Product ${i + 1}`}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {fields.map(field => (
            <tr key={field}>
              <th>{label(field)}</th>
              {records.map((record, i) => {
                const vars = Array.isArray(record.variants) ? record.variants.filter(isRecord) : [];
                const v = vars.find((item) => item.is_default) ?? vars[0];
                const val =
                  field === "price"
                    ? [
                        text(record.currency ?? (isRecord(v) ? v.currency : undefined)),
                        text(record.price ?? record.sale_price ?? (isRecord(v) ? v.price : undefined)),
                      ]
                        .filter(Boolean)
                        .join(" ") || "—"
                    : text(record[field]) || "—";
                return <td key={i}>{val}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function RecordCards({
  message, onSend, disabled, onAction, onProductSelection,
}: {
  message: MasterChatbotMessage;
  onSend?: (message: string) => void;
  disabled?: boolean;
  onAction?: (action: CardAction) => void;
  selectedProductIds?: string[];
  onProductSelection?: (productId: string, selected: boolean) => void;
}) {
  const [limit, setLimit] = useState(5);
  const [selected, setSelected] = useState<number[]>([]);
  const [comparisonOpen, setComparisonOpen] = useState(false);

  const records = extractRecords(message.data);
  // Filter out address records — they are never shown as cards
  const nonAddressRecords = records.filter(r => !detectAddressCard(r));
  const flow = typeof message.metadata?.flow === "string" ? message.metadata.flow : undefined;
  const isComparisonResult = message.metadata?.presentation === "comparison";
  const capabilities = Array.isArray(message.metadata?.capabilities) ? message.metadata.capabilities : [];

  // Plain text responses (action confirmations) — no cards
  if (message.metadata?.presentation === "text") return <>{message.content}</>;

  // Address-only responses or empty — show text only
  if (!nonAddressRecords.length) return <>{message.content}</>;

  const intro = /^(I completed `|Here (?:is|are) (?:the|\d+) results?)/i.test(message.content.trim())
    ? ""
    : message.content;

  const flowAction: "cancel" | "return_refund" | undefined =
    flow === "cancel_order"  ? "cancel" :
    flow === "return_refund" ? "return_refund" :
    undefined;

  const canSelectForCompare = !flowAction && !isComparisonResult;

  // Fix: call onProductSelection outside setSelected updater to avoid setState-during-render
  const toggleSelect = (index: number) => {
    const isCurrentlySelected = selected.includes(index);
    const productId = normalizeId(nonAddressRecords[index] ?? {}, ["product_id", "productId", "id"]);
    setSelected(current =>
      isCurrentlySelected
        ? current.filter(i => i !== index)
        : [...current.slice(-3), index],
    );
    if (productId && onProductSelection) {
      onProductSelection(productId, !isCurrentlySelected);
    }
  };

  // If this message IS a comparison result, show the table directly
  if (isComparisonResult && nonAddressRecords.length > 1) {
    return (
      <div className="master-chatbot-record-results">
        {intro && <p className="master-chatbot-record-intro">{intro}</p>}
        <ComparisonTable records={nonAddressRecords.slice(0, 4)} />
      </div>
    );
  }

  return (
    <div className="master-chatbot-record-results">
      {intro && <p className="master-chatbot-record-intro">{intro}</p>}

      <div className="master-chatbot-record-list">
        {nonAddressRecords.slice(0, limit).map((record, index) => (
          <RecordCard
            key={index}
            record={record}
            index={index}
            onSend={onSend}
            disabled={disabled}
            canAdd={capabilities.includes("add_to_cart")}
            selected={selected.includes(index)}
            onToggleSelect={() => toggleSelect(index)}
            canSelect={canSelectForCompare}
            flowAction={flowAction}
            onAction={onAction}
          />
        ))}
      </div>

      {limit < nonAddressRecords.length && (
        <button
          type="button"
          className="master-chatbot-record-more"
          onClick={() => setLimit(l => l + 5)}
        >
          Show more ({nonAddressRecords.length - limit} remaining)
        </button>
      )}

      {/* Compare bar — appears after product list when 2+ selected */}
      {canSelectForCompare && selected.length >= 2 && (
        <div className="master-chatbot-compare-bar">
          <button
            type="button"
            disabled={disabled}
            className="master-chatbot-compare-btn"
            onClick={() => setComparisonOpen(true)}
          >
            Compare
          </button>
          <button
            type="button"
            className="master-chatbot-compare-clear"
            onClick={() => { setSelected([]); setComparisonOpen(false); }}
          >
            Cancel
          </button>
        </div>
      )}

      {/* Comparison table — shown after cards, only once Compare is clicked */}
      {canSelectForCompare && comparisonOpen && selected.length >= 2 && (
        <ComparisonTable records={selected.map(i => nonAddressRecords[i])} />
      )}
    </div>
  );
}
