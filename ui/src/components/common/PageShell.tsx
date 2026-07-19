interface PageShellProps {
  title: string;
  question: string;
  children?: React.ReactNode;
}

export function PageShell({ title, question, children }: PageShellProps) {
  const { pathname } = useLocation();
  const detailBreadcrumbs =
    pathname === "/sessions/diff"
      ? [{ label: "Sessions", to: "/sessions" }, { label: "Session diff" }]
      : pathname.startsWith("/sessions/")
        ? [{ label: "Sessions", to: "/sessions" }, { label: title }]
        : null;
  return (
    <div>
      <header className="page-header">
        <div>
          {detailBreadcrumbs ? (
            <div className="mb-2">
              <Breadcrumbs items={detailBreadcrumbs} />
            </div>
          ) : null}
          <p className="page-kicker">Cairn / field intelligence</p>
          <h1 className="page-title">{title}</h1>
          <p className="page-question">{question}</p>
        </div>
        <span className="page-status">
          <span className="mr-2 h-1.5 w-1.5 rounded-full bg-patina" aria-hidden="true" />
          Data stays on this device
        </span>
      </header>
      {children ?? (
        <div className="card empty-state">
          <h2>Nothing here yet</h2>
          <p className="mt-2 text-sm">
            Run <span className="mono text-copper">cairn sync</span> to ingest agent logs, or check
            Settings to enable adapters.
          </p>
        </div>
      )}
    </div>
  );
}
import { useLocation } from "react-router-dom";
import { Breadcrumbs } from "@/components/ui";
