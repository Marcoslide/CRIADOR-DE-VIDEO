import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import { Layout } from "../components/Layout";
import type { PillState } from "../components/StatusPill";
import { StatusPill } from "../components/StatusPill";

function toPillState(status: string | undefined, isError: boolean, isPending: boolean): PillState {
  if (isPending) return "checking";
  if (isError) return "error";
  if (status === "connected" || status === "ok") return "connected";
  if (status === "timeout") return "timeout";
  if (status === "not_configured") return "not_configured";
  return "error";
}

export function Dashboard() {
  const apiHealth = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 10_000,
  });

  const readiness = useQuery({
    queryKey: ["health", "ready"],
    queryFn: api.readiness,
    refetchInterval: 10_000,
  });

  const worker = useQuery({
    queryKey: ["health", "worker"],
    queryFn: api.workerHealth,
    refetchInterval: 15_000,
  });

  const postgres = readiness.data?.checks.find((c) => c.name === "postgres");
  const redis = readiness.data?.checks.find((c) => c.name === "redis");

  const cards = [
    {
      key: "api",
      label: "API",
      detail: apiHealth.data ? `v${apiHealth.data.version} · ${apiHealth.data.app_env}` : "—",
      state: toPillState(apiHealth.data?.status, apiHealth.isError, apiHealth.isPending),
      latency: null as number | null,
    },
    {
      key: "postgres",
      label: "PostgreSQL",
      detail: postgres?.detail ?? "Banco principal",
      state: toPillState(postgres?.status, readiness.isError, readiness.isPending),
      latency: postgres?.latency_ms ?? null,
    },
    {
      key: "redis",
      label: "Redis",
      detail: redis?.detail ?? "Cache / broker",
      state: toPillState(redis?.status, readiness.isError, readiness.isPending),
      latency: redis?.latency_ms ?? null,
    },
    {
      key: "worker",
      label: "Celery Worker",
      detail: worker.data?.detail ?? "Round-trip via Redis",
      state: toPillState(worker.data?.status, worker.isError, worker.isPending),
      latency: worker.data?.latency_ms ?? null,
    },
  ];

  return (
    <Layout title="Dashboard">
      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
          Status do sistema
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {cards.map((card) => (
            <div
              key={card.key}
              className="rounded-xl border border-base-700 bg-base-900 p-4 shadow-sm"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-slate-200">{card.label}</span>
                <StatusPill state={card.state} />
              </div>
              <p className="mt-3 truncate text-xs text-slate-500" title={card.detail}>
                {card.detail}
              </p>
              {card.latency !== null && (
                <p className="mt-1 text-xs text-slate-600">{card.latency.toFixed(1)} ms</p>
              )}
            </div>
          ))}
        </div>
      </section>

      <section className="mt-8 rounded-xl border border-base-700 bg-base-900 p-5">
        <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500">
          Fase atual
        </h2>
        <p className="mt-2 text-sm text-slate-300">
          <span className="font-semibold text-slate-100">Fase 1 — Foundation.</span>{" "}
          Monorepo, API, banco de dados, fila e frontend rodando de ponta a ponta. As demais
          telas do menu lateral são ativadas fase a fase, conforme o{" "}
          <code className="rounded bg-base-800 px-1 py-0.5 text-slate-300">ROADMAP.md</code> —
          nada aqui simula funcionalidade que ainda não existe.
        </p>
      </section>
    </Layout>
  );
}
