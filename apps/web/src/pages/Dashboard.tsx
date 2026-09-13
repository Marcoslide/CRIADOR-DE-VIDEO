import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import type { EngineStatusValue, SystemStatusResponse } from "../api/types";
import { Layout } from "../components/Layout";
import type { PillState } from "../components/StatusPill";
import { StatusPill } from "../components/StatusPill";

function toPillState(state: EngineStatusValue | string | undefined, isError: boolean, isPending: boolean): PillState {
  if (isPending) return "checking";
  if (isError) return "error";
  if (state === "connected" || state === "ok") return "connected";
  if (state === "timeout") return "timeout";
  if (state === "not_configured" || state === "not_installed") return "not_configured";
  if (state === "auth_expired") return "auth_expired";
  if (state === "connecting") return "connecting";
  if (state === "degraded") return "degraded";
  return "error";
}

function storageDetail(data: SystemStatusResponse | undefined): string {
  const storage = data?.storage;
  if (!storage) return "Google Drive — 18 pastas oficiais";
  if (storage.status !== "connected" && storage.detail) return storage.detail;
  if (storage.tree) return `${storage.tree.found.length}/${storage.tree.expected.length} pastas oficiais encontradas`;
  return storage.detail ?? "Google Drive — 18 pastas oficiais";
}

export function Dashboard() {
  const status = useQuery({
    queryKey: ["status", "system"],
    queryFn: api.systemStatus,
    refetchInterval: 15_000,
  });

  const d = status.data;
  const isPending = status.isPending;
  const isError = status.isError;

  const coreCards = [
    {
      key: "api",
      label: "API",
      detail: d ? "Processo de pé" : "—",
      state: toPillState(d?.api.status, isError, isPending),
      latency: d?.api.latency_ms ?? null,
    },
    {
      key: "postgres",
      label: "PostgreSQL",
      detail: d?.postgres.detail ?? "Banco principal",
      state: toPillState(d?.postgres.status, isError, isPending),
      latency: d?.postgres.latency_ms ?? null,
    },
    {
      key: "redis",
      label: "Redis",
      detail: d?.redis.detail ?? "Cache / broker",
      state: toPillState(d?.redis.status, isError, isPending),
      latency: d?.redis.latency_ms ?? null,
    },
    {
      key: "worker",
      label: "Celery Worker",
      detail: d?.worker.detail ?? "Round-trip via Redis",
      state: toPillState(d?.worker.status, isError, isPending),
      latency: d?.worker.latency_ms ?? null,
    },
  ];

  const integrationCards = [
    {
      key: "storage",
      label: "Storage (Drive)",
      detail: storageDetail(d),
      state: toPillState(d?.storage.status, isError, isPending),
    },
    {
      key: "gpu",
      label: "GPU Engine",
      detail: d?.gpu.device_name ?? d?.gpu.detail ?? "Hostinger RTX 5090",
      state: toPillState(d?.gpu.status, isError, isPending),
    },
    {
      key: "openai",
      label: "OpenAI (Director AI)",
      detail: d?.openai.detail ?? "Planejamento de cenas — Fase 5",
      state: toPillState(d?.openai.status, isError, isPending),
    },
    {
      key: "unreal",
      label: "Unreal Engine",
      detail: d?.unreal.detail ?? "Motor de render — Fase 7/8",
      state: toPillState(d?.unreal.status, isError, isPending),
    },
    {
      key: "audio2face",
      label: "Audio2Face",
      detail: d?.audio2face.detail ?? "Performance facial — Fase 7",
      state: toPillState(d?.audio2face.status, isError, isPending),
    },
    {
      key: "metahuman",
      label: "MetaHuman Animator",
      detail: d?.metahuman.detail ?? "Animação corporal — Fase 7",
      state: toPillState(d?.metahuman.status, isError, isPending),
    },
  ];

  return (
    <Layout title="Dashboard">
      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
          Infraestrutura core
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {coreCards.map((card) => (
            <div key={card.key} className="rounded-xl border border-base-700 bg-base-900 p-4 shadow-sm">
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

      <section className="mt-8">
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
          Integrações e engines
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {integrationCards.map((card) => (
            <div key={card.key} className="rounded-xl border border-base-700 bg-base-900 p-4 shadow-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium text-slate-200">{card.label}</span>
                <StatusPill state={card.state} />
              </div>
              <p className="mt-3 truncate text-xs text-slate-500" title={card.detail}>
                {card.detail}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="mt-8 rounded-xl border border-base-700 bg-base-900 p-5">
        <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500">Fase atual</h2>
        <p className="mt-2 text-sm text-slate-300">
          <span className="font-semibold text-slate-100">Fase 1 — Foundation concluída.</span>{" "}
          <span className="font-semibold text-slate-100">Fase 2 — Storage concluída</span>{" "}
          com Google Drive real, streaming, retry e proteção contra exclusão permanente.{" "}
          <span className="font-semibold text-slate-100">Fase 3 — Avatar Registry</span> em
          fundação: CRUD real com máquina de estados, persistindo no PostgreSQL. Os cards acima
          mostram <span className="text-slate-100">Não configurado</span> /{" "}
          <span className="text-slate-100">Não instalado</span> honestamente até cada
          integração real existir — nada aqui simula funcionalidade que ainda não existe.
        </p>
        {isError && (
          <p className="mt-3 text-xs text-red-400">
            Falha ao consultar /status/system — verifique se a API está no ar.
          </p>
        )}
      </section>
    </Layout>
  );
}
