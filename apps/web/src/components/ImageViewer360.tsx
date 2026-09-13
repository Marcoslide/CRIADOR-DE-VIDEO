import { useMutation } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { api } from "../api/client";
import type { MultiviewFamilyProgress, ReferenceAssetCategory, RejectionReason } from "../api/types";
import { REJECTION_REASONS } from "../api/types";

const STATE_STYLE: Record<string, string> = {
  missing: "bg-base-800 text-slate-500 ring-base-700",
  uploaded: "bg-sky-500/10 text-sky-400 ring-sky-500/30",
  qa_pending: "bg-amber-500/10 text-amber-400 ring-amber-500/30",
  approved: "bg-emerald-500/10 text-emerald-400 ring-emerald-500/30",
  rejected: "bg-red-500/10 text-red-400 ring-red-500/30",
};

interface Props {
  avatarId: string;
  title: string;
  category: ReferenceAssetCategory;
  family: MultiviewFamilyProgress;
  actor: string;
  onMutated: () => void;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "erro desconhecido";
}

export function ImageViewer360({ avatarId, title, category, family, actor, onMutated }: Props) {
  const [angle, setAngle] = useState(0);
  const [rejectReason, setRejectReason] = useState<RejectionReason>("other");
  const [rejectNotes, setRejectNotes] = useState("");
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const slot = useMemo(() => family.slots.find((s) => s.angle === angle), [family, angle]);

  const referencesQuery = useMemo(() => slot?.asset_id, [slot]);

  const approve = useMutation({
    mutationFn: async () => {
      if (!slot?.asset_id) throw new Error("nenhum asset neste ângulo");
      const assets = await api.listReferences(avatarId);
      const asset = assets.find((a) => a.id === slot.asset_id);
      if (!asset) throw new Error("asset não encontrado");
      return api.approveReference(avatarId, asset.id, asset.version, actor);
    },
    onSuccess: () => {
      setError(null);
      onMutated();
    },
    onError: (e: unknown) => setError(errorMessage(e)),
  });

  const reject = useMutation({
    mutationFn: async () => {
      if (!slot?.asset_id) throw new Error("nenhum asset neste ângulo");
      const assets = await api.listReferences(avatarId);
      const asset = assets.find((a) => a.id === slot.asset_id);
      if (!asset) throw new Error("asset não encontrado");
      return api.rejectReference(avatarId, asset.id, {
        expected_version: asset.version,
        reason: rejectReason,
        notes: rejectNotes || undefined,
        reviewed_by: actor,
      });
    },
    onSuccess: () => {
      setError(null);
      setShowRejectForm(false);
      setRejectNotes("");
      onMutated();
    },
    onError: (e: unknown) => setError(errorMessage(e)),
  });

  const upload = useMutation({
    mutationFn: (file: File) => api.uploadReference(avatarId, file, { category, angle }),
    onSuccess: () => {
      setError(null);
      onMutated();
    },
    onError: (e: unknown) => setError(errorMessage(e)),
  });

  const busy = approve.isPending || reject.isPending || upload.isPending;

  return (
    <div className="rounded-xl border border-base-700 bg-base-900 p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-200">{title}</h3>
        <span className="text-xs text-slate-500">
          {family.done}/{family.total} aprovados
        </span>
      </div>

      <div className="mt-3 flex aspect-square w-full items-center justify-center overflow-hidden rounded-lg border border-base-700 bg-base-950">
        {referencesQuery ? (
          <img
            key={referencesQuery}
            src={api.referenceContentUrl(avatarId, referencesQuery)}
            alt={`${title} — ${angle}°`}
            className="h-full w-full object-cover"
          />
        ) : (
          <span className="text-xs text-slate-600">sem imagem em {angle}°</span>
        )}
      </div>

      <div className="mt-3 flex items-center gap-3">
        <input
          type="range"
          min={0}
          max={350}
          step={10}
          value={angle}
          onChange={(event) => {
            setAngle(Number(event.target.value));
            setShowRejectForm(false);
            setError(null);
          }}
          className="w-full accent-sky-500"
        />
        <span className="w-12 shrink-0 text-right text-xs text-slate-400">{angle}°</span>
      </div>

      <div className="mt-2 flex items-center justify-between">
        <span
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${STATE_STYLE[slot?.state ?? "missing"]}`}
        >
          {slot?.state ?? "missing"}
        </span>
        {slot?.asset_id && slot.state !== "approved" && (
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => approve.mutate()}
              className="rounded-md border border-emerald-700 px-2 py-1 text-[11px] font-medium text-emerald-400 hover:bg-emerald-500/10 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Aprovar
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => setShowRejectForm((v) => !v)}
              className="rounded-md border border-red-800 px-2 py-1 text-[11px] font-medium text-red-400 hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Rejeitar
            </button>
          </div>
        )}
      </div>

      <label className="mt-2 block cursor-pointer rounded-md border border-dashed border-base-700 px-3 py-1.5 text-center text-[11px] text-slate-400 hover:border-sky-500 hover:text-sky-400">
        {upload.isPending ? "Enviando…" : slot?.asset_id ? "Recapturar (nova versão)" : `Enviar imagem para ${angle}°`}
        <input
          type="file"
          accept="image/*"
          className="hidden"
          disabled={busy}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) upload.mutate(file);
            event.target.value = "";
          }}
        />
      </label>

      {error && <p className="mt-2 text-[11px] text-red-400">{error}</p>}

      {showRejectForm && (
        <div className="mt-3 space-y-2 rounded-md border border-base-700 bg-base-950 p-3">
          <select
            className="w-full rounded-md border border-base-700 bg-base-900 px-2 py-1.5 text-xs text-slate-200"
            value={rejectReason}
            onChange={(event) => setRejectReason(event.target.value as RejectionReason)}
          >
            {REJECTION_REASONS.map((reason) => (
              <option key={reason} value={reason}>
                {reason}
              </option>
            ))}
          </select>
          <input
            className="w-full rounded-md border border-base-700 bg-base-900 px-2 py-1.5 text-xs text-slate-200"
            placeholder="Notas (opcional)"
            value={rejectNotes}
            onChange={(event) => setRejectNotes(event.target.value)}
          />
          <button
            type="button"
            disabled={busy}
            onClick={() => reject.mutate()}
            className="w-full rounded-md bg-red-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-600 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Confirmar rejeição
          </button>
        </div>
      )}
    </div>
  );
}
