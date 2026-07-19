import { useQuery } from "@tanstack/react-query";
import { fetchWorkspace } from "@/lib/api";

export interface AdapterWarning {
  adapter_id: string;
  message: string;
  issue_url: string;
}

export function AdapterWarningBanner({ warnings }: { warnings: AdapterWarning[] }) {
  if (warnings.length === 0) return null;
  const warning = warnings[0]!;
  return (
    <div
      role="alert"
      className="border-b border-cinnabar/40 bg-cinnabar/10 px-6 py-2 text-sm text-bone"
    >
      <span>{warning.message}</span>{" "}
      <a
        className="font-mono text-[11px] text-copper underline underline-offset-2"
        href={warning.issue_url}
        target="_blank"
        rel="noreferrer"
      >
        Open a prefilled adapter issue
      </a>
      {warnings.length > 1 ? (
        <span className="ml-2 font-mono text-[10px] text-cinder">+{warnings.length - 1} more</span>
      ) : null}
    </div>
  );
}

export function AdapterHealthBanner() {
  const { data } = useQuery({
    queryKey: ["workspace"],
    queryFn: fetchWorkspace,
    staleTime: 60_000,
  });
  const raw = data?.health?.adapter_warnings;
  const warnings = Array.isArray(raw) ? (raw as AdapterWarning[]) : [];
  return <AdapterWarningBanner warnings={warnings} />;
}
