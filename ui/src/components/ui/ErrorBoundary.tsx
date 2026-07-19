import { Component, type ErrorInfo, type ReactNode } from "react";
import { InlineError } from "./Feedback";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo): void {
    // The boundary is intentionally local-only and does not emit telemetry.
  }

  render() {
    if (!this.state.error) return this.props.children;
    if (this.props.fallback) return this.props.fallback;
    return (
      <InlineError
        message="This local view could not be rendered."
        onRetry={() => this.setState({ error: null })}
      />
    );
  }
}
