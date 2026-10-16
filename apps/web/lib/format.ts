export function money(value: string | number | null | undefined, currency = "USD"): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(n);
}

export function day(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function when(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function cadence(days: number): string {
  return ({ 7: "weekly", 14: "every 2 weeks", 30: "monthly", 91: "quarterly", 365: "yearly" } as Record<number, string>)[days] || `every ${days} days`;
}
