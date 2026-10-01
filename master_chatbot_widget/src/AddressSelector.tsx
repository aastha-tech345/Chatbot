import { useState } from "react";
import { MapPin } from "lucide-react";

export interface AddressRecord {
  id?: unknown;
  address_id?: unknown;
  recipient_name?: unknown;
  line1?: unknown;
  line2?: unknown;
  city?: unknown;
  state?: unknown;
  postal_code?: unknown;
  is_default?: unknown;
  [key: string]: unknown;
}

interface AddressSelectorProps {
  addresses: AddressRecord[];
  disabled?: boolean;
  onSelect: (address: AddressRecord) => void;
}

function addressId(a: AddressRecord): string {
  return String(a.address_id ?? a.id ?? "");
}

function addressLabel(a: AddressRecord): string {
  return [a.recipient_name, a.line1, a.line2, a.city, a.state, a.postal_code]
    .filter(Boolean)
    .map(String)
    .join(", ");
}

function isDefault(a: AddressRecord): boolean {
  return a.is_default === true || a.is_default === 1 || a.is_default === "true";
}

export function AddressSelector({ addresses, disabled, onSelect }: AddressSelectorProps) {
  const defaultId = addresses.find(isDefault) ? addressId(addresses.find(isDefault)!) : addressId(addresses[0] ?? {});
  const [selected, setSelected] = useState(defaultId);

  if (!addresses.length) return <p>No saved addresses found.</p>;

  return (
    <div className="master-chatbot-address-selector">
      <p className="master-chatbot-address-selector-hint">Select the address to set as default:</p>
      {addresses.map((addr, i) => {
        const id = addressId(addr);
        const inputId = `addr-radio-${id || i}`;
        const checked = selected === id;
        return (
          <label
            key={id || i}
            htmlFor={inputId}
            className={`master-chatbot-address-option${checked ? " is-selected" : ""}${isDefault(addr) ? " is-default" : ""}`}
          >
            <input
              id={inputId}
              type="radio"
              name="address-select"
              value={id}
              checked={checked}
              disabled={disabled}
              onChange={() => setSelected(id)}
            />
            <MapPin size={14} className="master-chatbot-address-icon" />
            <span className="master-chatbot-address-text">
              {addressLabel(addr)}
              {isDefault(addr) && <em className="master-chatbot-address-badge"> (current default)</em>}
            </span>
          </label>
        );
      })}
      <button
        type="button"
        className="master-chatbot-address-confirm"
        disabled={disabled || !selected}
        onClick={() => {
          const addr = addresses.find(a => addressId(a) === selected);
          if (addr) onSelect(addr);
        }}
      >
        Set as default address
      </button>
    </div>
  );
}

/** Extract only the default address from a list, formatted as plain text */
export function extractDefaultAddress(addresses: AddressRecord[]): string | null {
  const def = addresses.find(isDefault) ?? addresses[0];
  if (!def) return null;
  return addressLabel(def);
}
