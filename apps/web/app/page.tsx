import { AGENTS } from "@/lib/agents";

const PROTOTYPE_URL = "https://claude.ai/code/artifact/7aa6dee3-6fc6-4628-a120-fb17d8fa1e45";

export default function Home() {
  return (
    <main className="min-h-screen bg-ink-950 px-6 py-16 sm:px-12">
      <div className="mx-auto max-w-5xl">
        <header className="mb-12">
          <p className="mb-2 text-sm uppercase tracking-widest text-terracotta-400">
            Milo
          </p>
          <h1 className="text-4xl font-semibold text-white sm:text-5xl">
            Your agent, always on.
          </h1>
          <p className="mt-4 max-w-xl text-white/60">
            A high-autonomy AI assistant that orchestrates a fleet of
            specialized agents — research, email, documents, files,
            monitoring, and human-approved transactions — across any model.
          </p>
        </header>

        <section aria-labelledby="fleet-heading" className="mb-12">
          <h2
            id="fleet-heading"
            className="mb-4 text-xs font-medium uppercase tracking-widest text-white/40"
          >
            The fleet
          </h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {AGENTS.map((agent) => (
              <div key={agent.id} className="glass p-5">
                <h3 className="text-lg font-medium text-white">{agent.name}</h3>
                <p className="mt-1 text-sm text-white/60">{agent.role}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="glass p-6">
          <p className="text-sm text-white/50">
            The live console isn&apos;t wired up yet — this is the scaffold
            for the real backend, not the interactive prototype.
          </p>
          <a
            href={PROTOTYPE_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-4 inline-flex items-center gap-2 rounded-lg bg-terracotta-500 px-5 py-2.5 text-sm font-medium text-ink-950 transition hover:bg-terracotta-400"
          >
            Try the interactive prototype →
          </a>
          <p className="mt-2 text-xs text-white/40">
            Full click-through demo — chat, agent roster, pricing,
            suggestions, waitlist. Simulated responses today, not this live
            backend yet.
          </p>
        </section>
      </div>
    </main>
  );
}
