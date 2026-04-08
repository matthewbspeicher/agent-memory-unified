// frontend/src/components/competition/CompetitionErrorBoundary.tsx
import { Component, type ReactNode } from 'react';

interface Props { children: ReactNode }
interface State { hasError: boolean }

export class CompetitionErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-4 bg-red-900/20 border border-red-800 rounded">
          <h3 className="font-semibold text-red-400">Competition Error</h3>
          <p className="text-red-500 text-sm">
            Unable to load competition data. The arena will retry automatically.
          </p>
        </div>
      );
    }
    return this.props.children;
  }
}
