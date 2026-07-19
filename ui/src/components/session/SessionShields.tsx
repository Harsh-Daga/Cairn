import { Link } from "react-router-dom";
import type { SessionShield } from "@/lib/types";
import { Chip } from "@/components/common/Chip";

export function SessionShields({ shields }: { shields: SessionShield[] }) {
  return (
    <section className="card p-4" aria-label="Session shields">
      <p className="font-mono text-[9px] uppercase tracking-wide text-cinder">
        Independent session facts · not one trust score
      </p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {shields.map((shield) => (
          <article key={shield.shield} className="rounded-sm border border-quartz-vein p-3">
            <div className="flex items-center justify-between gap-2">
              <h2 className="font-display text-sm capitalize text-bone">{shield.shield} shield</h2>
              <Chip
                label={shield.state}
                tone={shield.state === "attention" ? "cinnabar" : "estimated"}
              />
            </div>
            <p className="mt-2 text-xs text-bone">{shield.summary}</p>
            <ul className="mt-2 space-y-1 text-[10px] leading-4 text-cinder">
              {shield.facts.map((fact) => (
                <li key={fact}>• {fact}</li>
              ))}
            </ul>
            <p className="mt-2 text-[10px] leading-4 text-ash">Limit: {shield.limitation}</p>
            <Link to={shield.action_path} className="mt-2 inline-flex text-xs text-copper">
              {shield.action_label}
            </Link>
          </article>
        ))}
      </div>
    </section>
  );
}
