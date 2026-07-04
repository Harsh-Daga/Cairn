interface PageShellProps {
  title: string;
  question: string;
  children?: React.ReactNode;
}

export function PageShell({ title, question, children }: PageShellProps) {
  return (
    <div>
      <h1 className="page-title">{title}</h1>
      <p className="page-question">{question}</p>
      {children ?? (
        <div className="card empty-state">
          <h2>Nothing here yet</h2>
          <p className="mt-2 text-sm">
            Run <span className="mono text-copper">cairn sync</span> to ingest agent logs, or
            check Settings to enable adapters.
          </p>
        </div>
      )}
    </div>
  );
}
