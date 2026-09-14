import { createClient } from "@supabase/supabase-js";

// Publishable (anon) key — safe to ship in client code by design, same key
// already embedded in the milo-lilac.vercel.app waitlist form.
export const SUPABASE_URL = "https://ptjwcliszbfpknyryzft.supabase.co";
export const SUPABASE_ANON_KEY = "sb_publishable_osrIFGSVeI2jzIxNzglskg_osNSaguQ";

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
  },
});
