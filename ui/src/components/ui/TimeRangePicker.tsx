import { useRef, useState } from "react";
import type { CustomTimeRange, TimeRange } from "@/lib/types";
import { Dialog } from "./Overlays";
import { LabeledField, SegmentedControl } from "./Controls";

const PRESETS: ReadonlyArray<{ value: TimeRange; label: string }> = [
  { value: "24h", label: "24h" },
  { value: "7d", label: "7d" },
  { value: "30d", label: "30d" },
  { value: "90d", label: "90d" },
];

export function TimeRangePicker({
  value,
  custom,
  onPreset,
  onCustom,
  customDisabled = false,
}: {
  value: TimeRange;
  custom?: CustomTimeRange | null;
  onPreset: (value: TimeRange) => void;
  onCustom: (value: CustomTimeRange) => void;
  customDisabled?: boolean;
}) {
  const now = new Date();
  const [open, setOpen] = useState(false);
  const [start, setStart] = useState(
    custom?.start ?? new Date(now.getTime() - 7 * 86_400_000).toISOString().slice(0, 16),
  );
  const [end, setEnd] = useState(custom?.end ?? now.toISOString().slice(0, 16));
  const [timezone, setTimezone] = useState(
    custom?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone ?? "UTC",
  );
  const [error, setError] = useState("");
  const startRef = useRef<HTMLInputElement>(null);
  const apply = () => {
    if (!start || !end || start >= end) {
      setError("Choose a start before the end.");
      return;
    }
    if (!timezone.trim()) {
      setError("Enter an IANA timezone.");
      return;
    }
    onCustom({ start, end, timezone: timezone.trim() });
    setError("");
    setOpen(false);
  };
  return (
    <div className="flex flex-wrap items-center gap-2">
      <SegmentedControl label="Time range" value={value} options={PRESETS} onChange={onPreset} />
      {!customDisabled ? (
        <>
          <button
            type="button"
            aria-pressed={custom != null}
            className="min-h-9 rounded-sm border border-quartz-vein px-3 font-mono text-xs text-cinder"
            onClick={() => setOpen(true)}
          >
            Custom
          </button>
          <Dialog
            open={open}
            title="Custom time range"
            onClose={() => setOpen(false)}
            initialFocusRef={startRef}
            footer={
              <>
                <button
                  type="button"
                  className="min-h-9 rounded-sm border border-quartz-vein px-3 text-xs"
                  onClick={() => setOpen(false)}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="min-h-9 rounded-sm border border-copper px-3 text-xs text-copper"
                  onClick={apply}
                >
                  Apply
                </button>
              </>
            }
          >
            <div className="space-y-3">
              <LabeledField label="Start" error={error || undefined}>
                <input
                  ref={startRef}
                  type="datetime-local"
                  value={start}
                  onChange={(event) => setStart(event.target.value)}
                  className="w-full rounded-sm border border-quartz-vein bg-shale px-3 py-2 text-bone"
                />
              </LabeledField>
              <LabeledField label="End">
                <input
                  type="datetime-local"
                  value={end}
                  onChange={(event) => setEnd(event.target.value)}
                  className="w-full rounded-sm border border-quartz-vein bg-shale px-3 py-2 text-bone"
                />
              </LabeledField>
              <LabeledField label="IANA timezone">
                <input
                  type="text"
                  value={timezone}
                  onChange={(event) => setTimezone(event.target.value)}
                  className="w-full rounded-sm border border-quartz-vein bg-shale px-3 py-2 text-bone"
                />
              </LabeledField>
            </div>
          </Dialog>
        </>
      ) : null}
    </div>
  );
}
