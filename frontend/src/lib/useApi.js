import { useEffect, useState } from "react";

// Fetch-on-mount for pages that render one API call. `fn` may be an inline
// arrow: re-fetch is driven by `deps`, not by `fn`'s identity. Returning a
// falsy promise (e.g. no analysis yet) leaves data null without an error.
export function useApiData(fn, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    Promise.resolve(fn())
      .then((d) => { if (!cancelled) setState({ data: d ?? null, error: null, loading: false }); })
      .catch((e) => { if (!cancelled) setState({ data: null, error: e.message, loading: false }); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}
