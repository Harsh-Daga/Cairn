import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "@/lib/api";
import { PageShell } from "@/components/common/PageShell";

export function OverviewPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
  });

  if (isLoading) {
    return (
      <PageShell title="Overview" question="What happened, and what should I look at?">
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError) {
    return (
      <PageShell title="Overview" question="What happened, and what should I look at?">
        <div className="card p-6 text-cinnabar">
          Couldn&apos;t reach the local server — is cairn running?
        </div>
      </PageShell>
    );
  }

  return (
    <PageShell title="Overview" question="What happened, and what should I look at?">
      <div className="card p-6">
        <p className="display text-xl text-bone">
          Cairn is ready — connect your agents and sync to begin surveying.
        </p>
        <p className="mt-2 mono text-[11px] text-cinder">
          server v{data?.version} · status {data?.status}
        </p>
      </div>
    </PageShell>
  );
}
