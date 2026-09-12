import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import type { Avatar, AvatarStatus } from "../api/types";
import { Layout } from "../components/Layout";

const STATUS_ORDER: AvatarStatus[] = [
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
];

function nextStatus(current: AvatarStatus): AvatarStatus | null {
  const index = STATUS_ORDER.indexOf(current);
  if (index === -1 || index === STATUS_ORDER.length - 1) return null;
  return STATUS_ORDER[index + 1];
}

// Remove marcas diacríticas combinantes (U+0300–U+036F) após normalizar para NFD — evita
// caracteres combinantes literais no código-fonte, que renderizam de forma instável.
const COMBINING_MARKS = /[̀-ͯ]/g;

function slugify(value: string): string {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(COMBINING_MARKS, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

function statusBadgeClass(status: AvatarStatus): string {
  if (status === "production_ready") return "bg-emerald-500/10 text-emerald-400 ring-emerald-500/30";
  if (status === "draft") return "bg-slate-500/10 text-slate-400 ring-slate-500/30";
  return "bg-sky-500/10 text-sky-400 ring-sky-500/30";
}

export function Avatars() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const avatars = useQuery({ queryKey: ["avatars"], queryFn: api.listAvatars });

  const createMutation = useMutation({
    mutationFn: () => api.createAvatar({ name, slug: slugify(name) }),
    onSuccess: () => {
      setName("");
      setFormError(null);
      void queryClient.invalidateQueries({ queryKey: ["avatars"] });
    },
    onError: (error: Error) => setFormError(error.message),
  });

  const advanceMutation = useMutation({
    mutationFn: (avatar: Avatar) => {
      const target = nextStatus(avatar.status);
      if (!target) throw new Error("já está em production_ready");
      return api.updateAvatarStatus(avatar.id, target);
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["avatars"] }),
  });

  return (
    <Layout title="Avatars">
      <section className="rounded-xl border border-base-700 bg-base-900 p-5">
        <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500">Novo avatar</h2>
        <form
          className="mt-3 flex flex-wrap items-end gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (!name.trim()) return;
            createMutation.mutate();
          }}
        >
          <div>
            <label className="block text-xs text-slate-500" htmlFor="avatar-name">
              Nome
            </label>
            <input
              id="avatar-name"
              className="mt-1 w-64 rounded-md border border-base-700 bg-base-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-sky-500"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Ana Executiva"
            />
          </div>
          {name.trim() && (
            <p className="pb-2 text-xs text-slate-600">slug: {slugify(name)}</p>
          )}
          <button
            type="submit"
            disabled={!name.trim() || createMutation.isPending}
            className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {createMutation.isPending ? "Criando…" : "Criar avatar"}
          </button>
        </form>
        {formError && <p className="mt-2 text-xs text-red-400">{formError}</p>}
      </section>

      <section className="mt-6">
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
          Avatares ({avatars.data?.length ?? 0})
        </h2>
        {avatars.isPending && <p className="text-sm text-slate-500">Carregando…</p>}
        {avatars.isError && (
          <p className="text-sm text-red-400">Falha ao carregar avatares — verifique a API.</p>
        )}
        {avatars.data?.length === 0 && (
          <p className="text-sm text-slate-500">Nenhum avatar criado ainda.</p>
        )}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {avatars.data?.map((avatar) => {
            const target = nextStatus(avatar.status);
            return (
              <div key={avatar.id} className="rounded-xl border border-base-700 bg-base-900 p-4">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-slate-200">{avatar.name}</span>
                  <span
                    className={`inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 ring-inset ${statusBadgeClass(avatar.status)}`}
                  >
                    {avatar.status}
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  {avatar.slug} · v{avatar.version}
                </p>
                <p className="mt-2 text-[11px] text-slate-600">
                  Atualizado {new Date(avatar.updated_at).toLocaleString("pt-BR")}
                </p>
                <button
                  type="button"
                  disabled={!target || advanceMutation.isPending}
                  onClick={() => advanceMutation.mutate(avatar)}
                  className="mt-3 w-full rounded-md border border-base-700 px-3 py-1.5 text-xs font-medium text-slate-300 hover:border-sky-500 hover:text-sky-400 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {target ? `Avançar para ${target}` : "Produção liberada"}
                </button>
              </div>
            );
          })}
        </div>
      </section>
    </Layout>
  );
}
