import { useParams } from "react-router-dom";
import { PageShell } from "@/components/common/PageShell";

export function SessionDetailPage() {
  const { id } = useParams<{ id: string }>();

  return (
    <PageShell
      title={`Session ${id ?? ""}`}
      question="Replay, inspect, and understand what happened."
    />
  );
}
