import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";

import { ApiError, api } from "../api/client";
import type {
  AvatarFactoryView,
  IdentityLock,
  IdentitySpec,
  QualityGateName,
  ReferenceAssetCategory,
  RejectionReason,
} from "../api/types";
import {
  EXPRESSION_CATEGORIES,
  FULL_BODY_360,
  HALF_BODY_360,
  HEAD_360,
  REJECTION_REASONS,
  SPECIALIZED_CATEGORIES,
} from "../api/types";
import { ImageViewer360 } from "../components/ImageViewer360";
import { Layout } from "../components/Layout";
import { SideBySideCompare } from "../components/SideBySideCompare";

const PIPELINE_STAGES = [
  "draft",
  "identity_locked",
  "multiview_in_progress",
  "multiview_approved",
  "mesh_in_progress",
  "mesh_approved",
  "rigged",
  "materials_approved",
  "face_approved",
  "voice_approved",
  "motion_approved",
  "master_approved",
  "production_ready",
] as const;

const GATE_LABELS: Record<QualityGateName, string> = {
  identity: "Identity Lock",
  multiview: "Multiview",
  mesh: "Mesh",
  rig: "Rig",
  materials: "Materials",
  face: "Face",
  voice: "Voice",
  motion: "Motion",
  master: "Master",
  production: "Production Ready",
};

const GATE_STATUS_CLASS: Record<string, string> = {
  not_tested: "bg-slate-500/10 text-slate-400 ring-slate-500/30",
  pass: "bg-emerald-500/10 text-emerald-400 ring-emerald-500/30",
  warn: "bg-amber-500/10 text-amber-400 ring-amber-500/30",
  fail: "bg-red-500/10 text-red-400 ring-red-500/30",
  requires_human: "bg-sky-500/10 text-sky-400 ring-sky-500/30",
  requires_model: "bg-sky-500/10 text-sky-400 ring-sky-500/30",
};

const CATEGORY_STATE_CLASS: Record<string, string> = {
  missing: "bg-base-800 text-slate-500 ring-base-700",
  uploaded: "bg-sky-500/10 text-sky-400 ring-sky-500/30",
  qa_pending: "bg-amber-500/10 text-amber-400 ring-amber-500/30",
  approved: "bg-emerald-500/10 text-emerald-400 ring-emerald-500/30",
  rejected: "bg-red-500/10 text-red-400 ring-red-500/30",
};

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "erro desconhecido";
}

function missingList(error: unknown): string[] | undefined {
  if (error instanceof ApiError && error.detail && typeof error.detail === "object" && "missing" in error.detail) {
    const missing = (error.detail as { missing?: unknown }).missing;
    if (Array.isArray(missing)) return missing as string[];
  }
  return undefined;
}

function IdentityLockPanel({
  avatarId,
  lock,
  onMutated,
}: {
  avatarId: string;
  lock: IdentityLock | null;
  onMutated: () => void;
}) {
  const [spec, setSpec] = useState<IdentitySpec>(
    lock?.identity_spec ?? {
      face: {},
      eyes: {},
      mouth: {},
      hair: {},
      body: {},
      hands: {},
      clothing: {},
    },
  );
  const [heightCm, setHeightCm] = useState(lock?.height_cm?.toString() ?? "");
  const [approver, setApprover] = useState("marcos");
  const [localError, setLocalError] = useState<string | null>(null);

  const canEdit = !lock || lock.status === "draft";

  const save = useMutation({
    mutationFn: () =>
      api.upsertIdentityLock(avatarId, {
        identity_spec: spec,
        height_cm: heightCm ? Number(heightCm) : undefined,
      }),
    onSuccess: () => {
      setLocalError(null);
      onMutated();
    },
    onError: (e: unknown) => setLocalError(errorMessage(e)),
  });

  const approve = useMutation({
    mutationFn: () => {
      if (!lock) throw new Error("nada para aprovar");
      return api.approveIdentityLock(avatarId, lock.version, approver);
    },
    onSuccess: () => {
      setLocalError(null);
      onMutated();
    },
    onError: (e: unknown) => setLocalError(errorMessage(e)),
  });

  return (
    <div className="mt-3 space-y-4">
      {lock && (
        <p className="text-xs text-slate-500">
          Versão de identidade {lock.identity_version} ·{" "}
          <span
            className={`rounded-full px-2 py-0.5 text-[11px] ring-1 ring-inset ${
              lock.status === "approved"
                ? "bg-emerald-500/10 text-emerald-400 ring-emerald-500/30"
                : "bg-sky-500/10 text-sky-400 ring-sky-500/30"
            }`}
          >
            {lock.status}
          </span>
          {lock.approved_by && ` · aprovado por ${lock.approved_by}`}
        </p>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {(
          [
            ["face", "face_shape", "Formato do rosto"],
            ["face", "nose_shape", "Formato do nariz"],
            ["eyes", "eye_color", "Cor dos olhos"],
            ["eyes", "eye_shape", "Formato dos olhos"],
            ["hair", "hair_color", "Cor do cabelo"],
            ["hair", "hairline", "Hairline"],
            ["body", "skin_tone", "Tom de pele"],
            ["body", "build", "Estrutura corporal"],
            ["mouth", "teeth_alignment", "Alinhamento dos dentes"],
          ] as const
        ).map(([group, field, label]) => (
          <div key={`${group}.${field}`}>
            <label className="block text-xs text-slate-500">{label}</label>
            <input
              disabled={!canEdit}
              className="mt-1 w-full rounded-md border border-base-700 bg-base-950 px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-sky-500 disabled:opacity-50"
              value={(spec[group] as Record<string, string | undefined>)[field] ?? ""}
              onChange={(event) =>
                setSpec((prev) => ({
                  ...prev,
                  [group]: { ...prev[group], [field]: event.target.value },
                }))
              }
            />
          </div>
        ))}
        <div>
          <label className="block text-xs text-slate-500">Altura (cm)</label>
          <input
            disabled={!canEdit}
            type="number"
            className="mt-1 w-full rounded-md border border-base-700 bg-base-950 px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-sky-500 disabled:opacity-50"
            value={heightCm}
            onChange={(event) => setHeightCm(event.target.value)}
          />
        </div>
      </div>

      {localError && <p className="text-xs text-red-400">{localError}</p>}

      <div className="flex flex-wrap items-center gap-3">
        {canEdit && (
          <button
            type="button"
            disabled={save.isPending}
            onClick={() => save.mutate()}
            className="rounded-md bg-sky-600 px-4 py-2 text-xs font-medium text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {lock ? "Salvar rascunho" : "Criar identity lock"}
          </button>
        )}
        {lock && lock.status === "draft" && (
          <>
            <input
              className="rounded-md border border-base-700 bg-base-950 px-2 py-1.5 text-xs text-slate-200"
              placeholder="aprovador"
              value={approver}
              onChange={(event) => setApprover(event.target.value)}
            />
            <button
              type="button"
              disabled={approve.isPending}
              onClick={() => approve.mutate()}
              className="rounded-md border border-emerald-700 px-4 py-2 text-xs font-medium text-emerald-400 hover:bg-emerald-500/10 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Aprovar identity lock
            </button>
          </>
        )}
        {lock && lock.status === "approved" && (
          <p className="text-xs text-slate-500">
            Aprovado — para mudar a identidade, edite os campos acima e salve (cria uma nova versão).
          </p>
        )}
      </div>
    </div>
  );
}

function CategoryGrid({
  avatarId,
  title,
  categories,
  progress,
  actor,
  onMutated,
}: {
  avatarId: string;
  title: string;
  categories: readonly ReferenceAssetCategory[];
  progress: AvatarFactoryView["multiview"]["specialized"];
  actor: string;
  onMutated: () => void;
}) {
  const [selected, setSelected] = useState<ReferenceAssetCategory | null>(null);
  const [reason, setReason] = useState<RejectionReason>("other");
  const [error, setError] = useState<string | null>(null);

  const byCategory = new Map(progress.map((p) => [p.category, p]));

  const upload = useMutation({
    mutationFn: (file: File) => api.uploadReference(avatarId, file, { category: selected! }),
    onSuccess: () => {
      setError(null);
      onMutated();
    },
    onError: (e: unknown) => setError(errorMessage(e)),
  });
  const approve = useMutation({
    mutationFn: ({ assetId, version }: { assetId: string; version: number }) =>
      api.approveReference(avatarId, assetId, version, actor),
    onSuccess: () => {
      setError(null);
      onMutated();
    },
    onError: (e: unknown) => setError(errorMessage(e)),
  });
  const reject = useMutation({
    mutationFn: ({ assetId, version }: { assetId: string; version: number }) =>
      api.rejectReference(avatarId, assetId, {
        expected_version: version,
        reason,
        reviewed_by: actor,
      }),
    onSuccess: () => {
      setError(null);
      onMutated();
    },
    onError: (e: unknown) => setError(errorMessage(e)),
  });

  const referencesQuery = useQuery({
    queryKey: ["avatar-references", avatarId, selected],
    queryFn: () => api.listReferences(avatarId, selected!),
    enabled: Boolean(selected),
  });
  const currentAsset = referencesQuery.data?.at(-1);

  return (
    <div className="mt-4">
      <p className="text-xs font-medium text-slate-400">
        {title} ({progress.filter((p) => p.state === "approved").length}/{categories.length})
      </p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {categories.map((category) => {
          const state = byCategory.get(category)?.state ?? "missing";
          return (
            <button
              key={category}
              type="button"
              onClick={() => setSelected(category === selected ? null : category)}
              className={`rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ring-inset ${CATEGORY_STATE_CLASS[state]} ${selected === category ? "outline outline-1 outline-sky-500" : ""}`}
            >
              {category}
            </button>
          );
        })}
      </div>

      {selected && (
        <div className="mt-3 rounded-lg border border-base-700 bg-base-950 p-3">
          <p className="text-xs text-slate-400">{selected}</p>
          {currentAsset && (
            <img
              src={api.referenceContentUrl(avatarId, currentAsset.id)}
              alt={selected}
              className="mt-2 h-40 w-40 rounded-md object-cover"
            />
          )}
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <label className="cursor-pointer rounded-md border border-base-700 px-3 py-1.5 text-[11px] text-slate-300 hover:border-sky-500">
              {upload.isPending ? "Enviando…" : "Enviar imagem"}
              <input
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) upload.mutate(file);
                  event.target.value = "";
                }}
              />
            </label>
            {currentAsset && currentAsset.upload_state !== "approved" && (
              <>
                <button
                  type="button"
                  onClick={() => approve.mutate({ assetId: currentAsset.id, version: currentAsset.version })}
                  className="rounded-md border border-emerald-700 px-3 py-1.5 text-[11px] text-emerald-400 hover:bg-emerald-500/10"
                >
                  Aprovar
                </button>
                <select
                  className="rounded-md border border-base-700 bg-base-900 px-2 py-1.5 text-[11px] text-slate-200"
                  value={reason}
                  onChange={(event) => setReason(event.target.value as RejectionReason)}
                >
                  {REJECTION_REASONS.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => reject.mutate({ assetId: currentAsset.id, version: currentAsset.version })}
                  className="rounded-md border border-red-800 px-3 py-1.5 text-[11px] text-red-400 hover:bg-red-500/10"
                >
                  Rejeitar
                </button>
              </>
            )}
          </div>
          {error && <p className="mt-2 text-[11px] text-red-400">{error}</p>}
        </div>
      )}
    </div>
  );
}

function HistorySection({ avatarId }: { avatarId: string }) {
  const history = useQuery({
    queryKey: ["avatar-history", avatarId],
    queryFn: () => api.getHistory(avatarId),
  });

  return (
    <section className="mt-6 rounded-xl border border-base-700 bg-base-900 p-5">
      <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500">Histórico</h2>
      {history.data?.length === 0 && <p className="mt-2 text-xs text-slate-500">Nenhuma transição ainda.</p>}
      <div className="mt-3 space-y-2">
        {history.data?.map((entry) => (
          <div key={entry.id} className="rounded-lg border border-base-700 bg-base-950 p-3 text-xs">
            <p className="text-slate-300">
              {entry.from_status} → {entry.to_status}{" "}
              <span className="text-slate-600">(gate: {entry.quality_gate ?? "—"})</span>
            </p>
            <p className="mt-1 text-slate-500">
              {entry.actor ?? "desconhecido"} · {new Date(entry.created_at).toLocaleString("pt-BR")}
            </p>
            {entry.reason && <p className="mt-1 text-slate-500">{entry.reason}</p>}
          </div>
        ))}
      </div>
    </section>
  );
}

export function AvatarFactory() {
  const { id: avatarId } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [actor, setActor] = useState("marcos");
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [globalMissing, setGlobalMissing] = useState<string[] | undefined>(undefined);

  const factory = useQuery({
    queryKey: ["avatar-factory", avatarId],
    queryFn: () => api.getFactoryView(avatarId!),
    enabled: Boolean(avatarId),
    refetchInterval: 15_000,
  });

  const onMutated = () => {
    setGlobalError(null);
    setGlobalMissing(undefined);
    void queryClient.invalidateQueries({ queryKey: ["avatar-factory", avatarId] });
    void queryClient.invalidateQueries({ queryKey: ["avatar-references", avatarId] });
    void queryClient.invalidateQueries({ queryKey: ["avatar-history", avatarId] });
  };

  const approveGate = useMutation({
    mutationFn: (gate: QualityGateName) =>
      api.approveGate(avatarId!, gate, { expected_version: factory.data!.version, actor }),
    onSuccess: onMutated,
    onError: (e: unknown) => {
      setGlobalError(errorMessage(e));
      setGlobalMissing(missingList(e));
    },
  });
  const rejectGate = useMutation({
    mutationFn: ({ gate, reason }: { gate: QualityGateName; reason: string }) =>
      api.rejectGate(avatarId!, gate, { expected_version: factory.data!.version, actor, reason }),
    onSuccess: onMutated,
    onError: (e: unknown) => setGlobalError(errorMessage(e)),
  });

  if (!avatarId) return null;

  if (factory.isPending) {
    return (
      <Layout title="Avatar Factory">
        <p className="text-sm text-slate-500">Carregando…</p>
      </Layout>
    );
  }
  if (factory.isError || !factory.data) {
    return (
      <Layout title="Avatar Factory">
        <p className="text-sm text-red-400">Falha ao carregar — avatar existe?</p>
      </Layout>
    );
  }

  const data = factory.data;
  const stageIndex = PIPELINE_STAGES.indexOf(data.status);

  return (
    <Layout title={`Avatar Factory — ${data.name}`}>
      <section className="rounded-xl border border-base-700 bg-base-900 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-lg font-semibold text-slate-100">{data.name}</p>
            <p className="text-xs text-slate-500">
              {data.slug} · v{data.version}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <label className="text-xs text-slate-500">
              Ator
              <input
                className="ml-2 w-28 rounded-md border border-base-700 bg-base-950 px-2 py-1 text-xs text-slate-200"
                value={actor}
                onChange={(event) => setActor(event.target.value)}
              />
            </label>
            <span
              className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ring-1 ring-inset ${
                data.readiness.production_ready
                  ? "bg-emerald-500/10 text-emerald-400 ring-emerald-500/30"
                  : "bg-sky-500/10 text-sky-400 ring-sky-500/30"
              }`}
            >
              {data.status}
            </span>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-1.5" title="Avatar → Identity Lock → References → Multiview → Mesh → Rig → Materials → Face → Voice → Motion → Master → Production Ready">
          {PIPELINE_STAGES.map((stage, i) => (
            <span key={stage} title={stage} className={`h-2 flex-1 rounded-full ${i <= stageIndex ? "bg-sky-500" : "bg-base-700"}`} />
          ))}
        </div>
        <p className="mt-1 text-[11px] text-slate-600">
          Etapa {stageIndex + 1} de {PIPELINE_STAGES.length}
        </p>
      </section>

      {globalError && (
        <div className="mt-4 rounded-xl border border-red-900 bg-red-950/40 p-3 text-xs text-red-300">
          <p>{globalError}</p>
          {globalMissing && globalMissing.length > 0 && (
            <ul className="mt-1 list-disc pl-4">
              {globalMissing.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <section className="mt-6 rounded-xl border border-base-700 bg-base-900 p-5">
        <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500">Identity Lock</h2>
        <IdentityLockPanel avatarId={avatarId} lock={data.identity_lock} onMutated={onMutated} />
      </section>

      <section className="mt-6 rounded-xl border border-base-700 bg-base-900 p-5">
        <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500">Referências / Multiview</h2>
        <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-3">
          <ImageViewer360
            avatarId={avatarId}
            title="Head 360°"
            category={HEAD_360}
            family={data.multiview.head_360}
            actor={actor}
            onMutated={onMutated}
          />
          <ImageViewer360
            avatarId={avatarId}
            title="Half Body 360°"
            category={HALF_BODY_360}
            family={data.multiview.half_body_360}
            actor={actor}
            onMutated={onMutated}
          />
          <ImageViewer360
            avatarId={avatarId}
            title="Full Body 360°"
            category={FULL_BODY_360}
            family={data.multiview.full_body_360}
            actor={actor}
            onMutated={onMutated}
          />
        </div>

        <CategoryGrid
          avatarId={avatarId}
          title="Referências especializadas"
          categories={SPECIALIZED_CATEGORIES}
          progress={data.multiview.specialized}
          actor={actor}
          onMutated={onMutated}
        />
        <CategoryGrid
          avatarId={avatarId}
          title="Expression master set"
          categories={EXPRESSION_CATEGORIES}
          progress={data.multiview.expression}
          actor={actor}
          onMutated={onMutated}
        />

        <p className="mt-4 text-xs text-slate-500">
          {data.multiview.all_required_approved
            ? "Todos os assets obrigatórios estão aprovados."
            : `Faltam assets ou existem ${data.multiview.open_rejections} rejeição(ões) aberta(s).`}
        </p>

        <div className="mt-4">
          <p className="mb-2 text-xs font-medium text-slate-400">
            Comparação: Reference Master (face_front_neutral) vs. Head 360° em 0°
          </p>
          <SideBySideCompare
            left={{
              label: "face_front_neutral",
              url: (() => {
                const masterId = data.multiview.specialized.find(
                  (item) => item.category === "face_front_neutral",
                )?.asset_id;
                return masterId ? api.referenceContentUrl(avatarId, masterId) : null;
              })(),
            }}
            right={{
              label: "head_360 @ 0°",
              url: (() => {
                const angleZeroId = data.multiview.head_360.slots.find((slot) => slot.angle === 0)?.asset_id;
                return angleZeroId ? api.referenceContentUrl(avatarId, angleZeroId) : null;
              })(),
            }}
          />
        </div>
      </section>

      <section className="mt-6 rounded-xl border border-base-700 bg-base-900 p-5">
        <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500">Quality Gates</h2>
        <div className="mt-3 space-y-2">
          {data.quality_gates.map((gate) => (
            <div
              key={gate.gate_name}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-base-700 bg-base-950 p-3"
            >
              <div>
                <p className="text-sm text-slate-200">{GATE_LABELS[gate.gate_name]}</p>
                {gate.reason && <p className="text-[11px] text-slate-500">{gate.reason}</p>}
              </div>
              <div className="flex items-center gap-2">
                <span className={`rounded-full px-2 py-0.5 text-[11px] ring-1 ring-inset ${GATE_STATUS_CLASS[gate.status]}`}>
                  {gate.status}
                </span>
                <button
                  type="button"
                  disabled={approveGate.isPending}
                  onClick={() => approveGate.mutate(gate.gate_name)}
                  className="rounded-md border border-emerald-700 px-2 py-1 text-[11px] font-medium text-emerald-400 hover:bg-emerald-500/10 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Aprovar
                </button>
                <button
                  type="button"
                  disabled={rejectGate.isPending}
                  onClick={() => rejectGate.mutate({ gate: gate.gate_name, reason: "revisão manual" })}
                  className="rounded-md border border-red-800 px-2 py-1 text-[11px] font-medium text-red-400 hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Rejeitar
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="mt-6 rounded-xl border border-base-700 bg-base-900 p-5">
        <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500">Production Readiness</h2>
        <ul className="mt-3 space-y-1.5">
          {data.readiness.requirements.map((requirement) => (
            <li key={requirement.key} className="flex items-center gap-2 text-sm">
              <span className={requirement.satisfied ? "text-emerald-400" : "text-slate-600"}>
                {requirement.satisfied ? "✓" : "○"}
              </span>
              <span className={requirement.satisfied ? "text-slate-300" : "text-slate-500"}>{requirement.label}</span>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-xs text-slate-500">
          Derived assets: {data.derived_assets.filter((a) => a.status !== "not_generated").length}/
          {data.derived_assets.length} gerados · Job contracts: {data.job_contracts.length} definidos (todos aguardando
          RTX 4090)
        </p>
      </section>

      <HistorySection avatarId={avatarId} />
    </Layout>
  );
}
