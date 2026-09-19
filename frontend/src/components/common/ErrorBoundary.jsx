import { Component } from "react";

/**
 * Last line of defence for a render that throws.
 *
 * Without one, a single bad render unmounts the whole tree and leaves a blank white
 * page with no way back except a manual reload. That is what an API error shaped
 * unexpectedly used to do to every page in this app. A boundary turns it into a page
 * the user can actually act on.
 *
 * Only render errors are caught here. Errors thrown inside event handlers and promises
 * never reach a boundary, so those still need their own try/catch.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Keep the stack in the console: the UI below deliberately does not show it, since
    // a component stack means nothing to a business owner.
    console.error("Unhandled render error:", error, info?.componentStack);
  }

  handleReset = () => {
    this.setState({ error: null });
  };

  render() {
    const { error } = this.state;
    if (!error) {
      return this.props.children;
    }

    return (
      <div className="grid min-h-screen place-items-center bg-surface px-4">
        <div className="w-full max-w-md rounded-2xl border border-line bg-white p-6 text-center shadow-sm">
          <h1 className="text-lg font-bold text-ink">This page stopped responding</h1>
          <p className="mt-2 text-sm text-muted">
            Something went wrong while displaying this page. Your data has not been changed.
          </p>
          <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:justify-center">
            <button
              type="button"
              className="rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white"
              onClick={this.handleReset}
            >
              Try again
            </button>
            <a
              href="/"
              className="rounded-xl border border-line px-4 py-2 text-sm font-semibold text-ink"
            >
              Go to the home page
            </a>
          </div>
        </div>
      </div>
    );
  }
}
