import { Component, type ReactNode } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';

interface ErrorBoundaryProps {
  children: ReactNode;
  area?: string;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: { componentStack: string }) {
    console.error(`[HERCULE:${this.props.area ?? 'app'}]`, error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex h-full w-full items-center justify-center bg-bg-primary p-6">
          <div className="card max-w-md p-6 text-center">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-red-500/10 text-red-400 border border-red-500/20">
              <AlertTriangle className="w-6 h-6" />
            </div>
            <h2 className="text-lg font-semibold text-text-primary">
              Something went wrong{this.props.area ? ` in ${this.props.area}` : ''}
            </h2>
            <p className="mt-1 text-sm text-text-tertiary">
              {this.state.error.message || 'An unexpected error occurred.'}
            </p>
            <button
              onClick={() => this.setState({ error: null })}
              className="btn-primary mt-4 px-4 py-2 text-sm rounded-lg inline-flex items-center gap-2"
            >
              <RotateCcw className="w-4 h-4" /> Try again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
