"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { useActiveHousehold } from "@/lib/store";

/** GET a household-scoped path and keep it fresh. `path` is appended to
 *  /households/{id} unless it starts with "/" (then it's used as-is with
 *  {hid} substituted). */
export function useHouseholdData<T>(path: string, fallback: T) {
  const household = useActiveHousehold();
  const [data, setData] = useState<T>(fallback);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!household) return;
    const url = path.startsWith("/") ? path.replace("{hid}", household.id) : `/households/${household.id}/${path}`;
    try {
      setData(await api<T>(url));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load this.");
    } finally {
      setLoading(false);
    }
  }, [household, path]);

  useEffect(() => {
    setLoading(true);
    void reload();
  }, [reload]);

  return { data, loading, error, reload, household };
}
