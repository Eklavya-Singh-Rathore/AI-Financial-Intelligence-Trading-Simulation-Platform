"use client";

import { AlertTriangle } from "lucide-react";
import { Component, type ReactNode } from "react";

type Props = { label?: string; children: ReactNode };
type State = { error: Error | null };

/** Containment for render-time failures: a crashing section degrades to an
 *  inline card with a retry, instead of taking down the whole route. Wrap
 *  data-heavy sections (charts, research tables) whose payloads come from
 *  external providers. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error) {
    // Surfaced for debugging; the fallback UI is the user-facing signal.
    console.error(`[${this.props.label ?? "section"}] render failed:`, error);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="rounded-lg border border-line bg-surface p-4">
          <div className="flex items-center gap-2 text-sm font-medium text-warn">
            <AlertTriangle size={15} />
            {this.props.label ?? "This section"} could not be displayed.
          </div>
          <p className="mt-1 text-xs text-ink-3">
            Something went wrong while rendering this section. The rest of the
            page keeps working.
          </p>
          <button
            type="button"
            onClick={() => this.setState({ error: null })}
            className="mt-2.5 rounded-md border border-line px-2.5 py-1 text-xs text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
