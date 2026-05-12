import { createContext, useContext, useId, useState, type ComponentType, type ReactNode } from 'react';
import { ChevronDown, Plus, X } from 'lucide-react';

export type SchemaField = {
  name: string;
  type: 'str' | 'int' | 'float' | 'bool' | 'dict' | 'list';
  description: string;
  required: boolean;
};

type SectionProps = {
  title: string;
  icon?: ComponentType<{ className?: string }>;
  defaultOpen?: boolean;
  children: ReactNode;
};

type FieldGroupProps = {
  label: string;
  helperText?: string;
  children: ReactNode;
};

type ToggleProps = {
  label: string;
  description?: string;
  value?: boolean;
  onChange: (value: boolean) => void;
};

type TextInputProps = {
  id?: string;
  label?: string;
  ariaLabel?: string;
  ariaLabelledBy?: string;
  value?: string;
  onChange: (value: string) => void;
  placeholder?: string;
  multiline?: boolean;
};

type NumberInputProps = {
  id?: string;
  label?: string;
  ariaLabel?: string;
  ariaLabelledBy?: string;
  value?: number;
  onChange: (value: number | undefined) => void;
  placeholder?: string;
  suffix?: string;
};

type SliderInputProps = {
  id?: string;
  label?: string;
  ariaLabel?: string;
  ariaLabelledBy?: string;
  value?: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number | undefined) => void;
  suffix?: string;
};

type SelectInputProps = {
  id?: string;
  label?: string;
  ariaLabel?: string;
  ariaLabelledBy?: string;
  options: string[];
  value?: string;
  onChange: (value: string) => void;
  placeholder?: string;
};

type MultiSelectorProps = {
  id?: string;
  label?: string;
  ariaLabel?: string;
  ariaLabelledBy?: string;
  options: string[];
  selected?: string[];
  onAdd: (value: string) => void;
  onRemove: (value: string) => void;
  getOptionLabel?: (value: string) => string;
  placeholder?: string;
};

type SchemaBuilderProps = {
  fields: SchemaField[];
  onChange: (fields: SchemaField[]) => void;
};

const inputClassName =
  'w-full rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-3 py-2 text-sm text-stone-900 outline-none transition placeholder:text-stone-400 focus:border-[#2f9b96] focus:ring-2 focus:ring-[#2f9b96]/25 disabled:cursor-not-allowed disabled:bg-[#f8e8c8]';

const schemaTypes: SchemaField['type'][] = ['str', 'int', 'float', 'bool', 'dict', 'list'];

type FieldGroupContextValue = {
  labelId: string;
  helperId?: string;
};

type AccessibleControlProps = {
  id?: string;
  label?: string;
  ariaLabel?: string;
  ariaLabelledBy?: string;
};

const FieldGroupContext = createContext<FieldGroupContextValue | null>(null);

function useAccessibleControl({ id, label, ariaLabel, ariaLabelledBy }: AccessibleControlProps) {
  const fieldGroup = useContext(FieldGroupContext);
  const explicitLabel = label ?? ariaLabel;

  return {
    id,
    'aria-label': explicitLabel,
    'aria-labelledby': explicitLabel ? undefined : ariaLabelledBy ?? fieldGroup?.labelId,
    'aria-describedby': fieldGroup?.helperId,
  };
}

export function parseOptionalFiniteNumber(value: string): number | undefined {
  if (value === '') {
    return undefined;
  }

  const parsedValue = Number(value);

  return Number.isFinite(parsedValue) ? parsedValue : undefined;
}

export function Section({ title, icon: Icon, defaultOpen = true, children }: SectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const contentId = useId();

  return (
    <section className="border-b border-[#7a5739]/30 py-4 last:border-b-0">
      <button
        type="button"
        aria-expanded={isOpen}
        aria-controls={contentId}
        onClick={() => setIsOpen((current) => !current)}
        className="flex w-full items-center justify-between gap-3 rounded-md px-2 py-2 text-left text-sm font-bold text-[#22170f] transition hover:bg-[#ffe6b3]"
      >
        <span className="flex min-w-0 items-center gap-2">
          {Icon ? <Icon className="h-4 w-4 shrink-0 text-[#2f9b96]" /> : null}
          <span className="truncate">{title}</span>
        </span>
        <ChevronDown
          aria-hidden="true"
          className={`h-4 w-4 shrink-0 text-stone-500 transition-transform ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>
      {isOpen ? (
        <div id={contentId} className="mt-3 space-y-4 px-2">
          {children}
        </div>
      ) : null}
    </section>
  );
}

export function FieldGroup({ label, helperText, children }: FieldGroupProps) {
  const labelId = useId();
  const helperId = useId();

  return (
    <FieldGroupContext.Provider value={{ labelId, helperId: helperText ? helperId : undefined }}>
      <div className="space-y-1.5">
      <div className="space-y-0.5">
        <div id={labelId} className="text-xs font-semibold uppercase tracking-wide text-stone-600">
          {label}
        </div>
        {helperText ? (
          <p id={helperId} className="m-0 text-xs leading-5 text-stone-500">
            {helperText}
          </p>
        ) : null}
      </div>
      {children}
      </div>
    </FieldGroupContext.Provider>
  );
}

export function Toggle({ label, description, value, onChange }: ToggleProps) {
  const enabled = value === true;

  return (
    <div className="ax-toggle-container">
      <div className="ax-toggle-content">
        <div className="ax-toggle-label">{label}</div>
        {description ? <p className="ax-toggle-desc">{description}</p> : null}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        aria-label={label}
        onClick={() => onChange(!enabled)}
        className="ax-toggle-switch"
      >
        <span aria-hidden="true" className="ax-toggle-thumb" />
      </button>
    </div>
  );
}

export function TextInput({
  id,
  label,
  ariaLabel,
  ariaLabelledBy,
  value,
  onChange,
  placeholder,
  multiline = false,
}: TextInputProps) {
  const accessibleProps = useAccessibleControl({ id, label, ariaLabel, ariaLabelledBy });

  if (multiline) {
    return (
      <textarea
        {...accessibleProps}
        value={value ?? ''}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        rows={4}
        className={`${inputClassName} min-h-28 resize-y leading-6`}
      />
    );
  }

  return (
    <input
      {...accessibleProps}
      type="text"
      value={value ?? ''}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      className={inputClassName}
    />
  );
}

export function NumberInput({ id, label, ariaLabel, ariaLabelledBy, value, onChange, placeholder, suffix }: NumberInputProps) {
  const accessibleProps = useAccessibleControl({ id, label, ariaLabel, ariaLabelledBy });

  return (
    <div className="relative">
      <input
        {...accessibleProps}
        type="number"
        value={value ?? ''}
        onChange={(event) => {
          onChange(parseOptionalFiniteNumber(event.target.value));
        }}
        placeholder={placeholder}
        className={`${inputClassName} ${suffix ? 'pr-12' : ''}`}
      />
      {suffix ? (
        <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-[10px] font-bold uppercase text-stone-400">
          {suffix}
        </span>
      ) : null}
    </div>
  );
}

function SliderControl({
  id,
  label,
  ariaLabel,
  ariaLabelledBy,
  value,
  min,
  max,
  step = 1,
  onChange,
  suffix,
}: SliderInputProps) {
  const accessibleProps = useAccessibleControl({ id, label, ariaLabel, ariaLabelledBy });
  const displayValue = value ?? min;

  return (
    <div className="flex items-center gap-3">
      <input
        {...accessibleProps}
        type="range"
        value={displayValue}
        min={min}
        max={max}
        step={step}
        onChange={(event) => onChange(parseOptionalFiniteNumber(event.target.value))}
        className="min-w-0 flex-1 accent-cyan-500"
      />
      <output className="min-w-14 rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-2 py-1 text-right text-xs font-bold text-stone-700">
        {displayValue}
        {suffix ? <span className="ml-1 text-[10px] uppercase text-stone-400">{suffix}</span> : null}
      </output>
    </div>
  );
}

export function SliderInput(props: SliderInputProps) {
  const { label } = props;

  return label ? (
    <FieldGroup label={label}>
      <SliderControl {...props} label={undefined} />
    </FieldGroup>
  ) : (
    <SliderControl {...props} />
  );
}

function SelectControl({ id, label, ariaLabel, ariaLabelledBy, options, value, onChange, placeholder }: SelectInputProps) {
  const accessibleProps = useAccessibleControl({ id, label, ariaLabel, ariaLabelledBy });

  return (
    <select
      {...accessibleProps}
      value={value ?? ''}
      onChange={(event) => onChange(event.target.value)}
      className={`${inputClassName} appearance-none`}
    >
      <option value="">{placeholder}</option>
      {options.map((option) => (
        <option key={option} value={option}>
          {option}
        </option>
      ))}
    </select>
  );
}

export function SelectInput(props: SelectInputProps) {
  const { label } = props;

  return label ? (
    <FieldGroup label={label}>
      <SelectControl {...props} label={undefined} />
    </FieldGroup>
  ) : (
    <SelectControl {...props} />
  );
}

function MultiSelectorControl({
  id,
  label,
  ariaLabel,
  ariaLabelledBy,
  options,
  selected = [],
  onAdd,
  onRemove,
  getOptionLabel = (value) => value,
  placeholder = 'Select...',
}: MultiSelectorProps) {
  const [pendingValue, setPendingValue] = useState('');
  const availableOptions = options.filter((option) => !selected.includes(option));
  const accessibleProps = useAccessibleControl({ id, label, ariaLabel, ariaLabelledBy });

  function handleAdd() {
    if (!pendingValue) {
      return;
    }

    onAdd(pendingValue);
    setPendingValue('');
  }

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <select
          {...accessibleProps}
          value={pendingValue}
          onChange={(event) => setPendingValue(event.target.value)}
          className={`${inputClassName} min-w-0 flex-1 appearance-none`}
        >
          <option value="">{placeholder}</option>
          {availableOptions.map((option) => (
            <option key={option} value={option}>
              {getOptionLabel(option)}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={handleAdd}
          disabled={!pendingValue}
          className="pixel-button inline-flex h-10 shrink-0 items-center justify-center gap-1 bg-[#2f9b96] px-3 text-sm font-bold text-white transition hover:bg-[#3fb0aa] disabled:cursor-not-allowed disabled:bg-stone-300 disabled:text-stone-500"
        >
          <Plus aria-hidden="true" className="h-4 w-4" />
          Add
        </button>
      </div>
      {selected.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {selected.map((item) => (
            <span
              key={item}
              className="inline-flex max-w-full items-center gap-1 rounded border border-[#7a5739]/40 bg-[#fffaf0] px-2.5 py-1 text-xs font-semibold text-stone-700"
            >
              <span className="truncate">{getOptionLabel(item)}</span>
              <button
                type="button"
                aria-label={`Remove ${getOptionLabel(item)}`}
                onClick={() => onRemove(item)}
                className="rounded p-0.5 text-stone-500 transition hover:bg-stone-200 hover:text-stone-800"
              >
                <X aria-hidden="true" className="h-3.5 w-3.5" />
              </button>
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function MultiSelector(props: MultiSelectorProps) {
  const { label } = props;

  return label ? (
    <FieldGroup label={label}>
      <MultiSelectorControl {...props} label={undefined} />
    </FieldGroup>
  ) : (
    <MultiSelectorControl {...props} />
  );
}

export function SchemaBuilder({ fields, onChange }: SchemaBuilderProps) {
  function updateField(index: number, patch: Partial<SchemaField>) {
    onChange(fields.map((field, fieldIndex) => (fieldIndex === index ? { ...field, ...patch } : field)));
  }

  function removeField(index: number) {
    onChange(fields.filter((_, fieldIndex) => fieldIndex !== index));
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-stone-600">Schema Fields</div>
          <p className="m-0 text-xs leading-5 text-stone-500">Define the structured output contract.</p>
        </div>
        <button
          type="button"
          onClick={() => onChange([...fields, { name: '', type: 'str', description: '', required: true }])}
          className="pixel-button inline-flex h-9 shrink-0 items-center justify-center gap-1.5 bg-[#2f9b96] px-3 text-sm font-bold text-white transition hover:bg-[#3fb0aa]"
        >
          <Plus aria-hidden="true" className="h-4 w-4" />
          Add field
        </button>
      </div>
      <div className="space-y-3">
        {fields.map((field, index) => (
          <div key={index} className="rounded-md border-2 border-[#7a5739] bg-[#fffaf0] p-3">
            <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_8rem_auto]">
              <input
                type="text"
                aria-label={`Field ${index + 1} name`}
                value={field.name}
                onChange={(event) => updateField(index, { name: event.target.value })}
                placeholder="Field name"
                className={inputClassName}
              />
              <select
                aria-label={`Field ${index + 1} type`}
                value={field.type}
                onChange={(event) => updateField(index, { type: event.target.value as SchemaField['type'] })}
                className={`${inputClassName} appearance-none`}
              >
                {schemaTypes.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
              <button
                type="button"
                aria-label={`Remove field ${index + 1}`}
                onClick={() => removeField(index)}
                className="inline-flex h-10 w-10 items-center justify-center rounded-md border-2 border-[#7a5739] bg-[#fffaf0] text-stone-500 transition hover:bg-[#ffe6b3] hover:text-stone-900"
              >
                <X aria-hidden="true" className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-[minmax(0,1fr)_8rem]">
              <input
                type="text"
                aria-label={`Field ${index + 1} description`}
                value={field.description}
                onChange={(event) => updateField(index, { description: event.target.value })}
                placeholder="Description"
                className={inputClassName}
              />
              <label className="flex h-10 items-center gap-2 rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-3 text-sm font-semibold text-stone-700">
                <input
                  type="checkbox"
                  checked={field.required}
                  onChange={(event) => updateField(index, { required: event.target.checked })}
                  className="h-4 w-4 rounded border-stone-300 text-cyan-400 focus:ring-cyan-300"
                />
                Required
              </label>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
