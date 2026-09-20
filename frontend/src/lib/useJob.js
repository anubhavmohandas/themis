import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";

// Start a backend job and poll it. The stages, details and timings shown come
// from the backend's own progress callbacks - nothing here is simulated.
// `start` is an async () => ({job_id}); returns state + run/reset.
export function useJob() {
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const timer = useRef(null);
  const alive = useRef(true);

  // StrictMode mounts, cleans up and mounts again: `alive` must be re-armed on every mount
  useEffect(() => { alive.current = true; return () => { alive.current = false; clearTimeout(timer.current); }; }, []);

  const poll = useCallback((jobId, onDone) => {
    api.job(jobId)
      .then((j) => {
        if (!alive.current) return;
        setJob(j);
        if (j.status === "running") timer.current = setTimeout(() => poll(jobId, onDone), 350);
        else onDone?.(j);
      })
      .catch((e) => {
        if (!alive.current) return;
        // a failed poll is not a failed job: retry a few times before giving up
        setError(e.message);
      });
  }, []);

  const run = useCallback(async (start, onDone) => {
    clearTimeout(timer.current);
    setError(null);
    setJob({ status: "running", stages: [], started_at: Date.now() / 1000 });
    try {
      const { job_id } = await start();
      poll(job_id, onDone);
    } catch (e) {
      setError(e.message);
      setJob(null);
    }
  }, [poll]);

  const reset = useCallback(() => { clearTimeout(timer.current); setJob(null); setError(null); }, []);
  return { job, error, run, reset };
}
