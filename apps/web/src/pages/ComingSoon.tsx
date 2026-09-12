import { Construction } from "lucide-react";

import { Layout } from "../components/Layout";

export function ComingSoon({ title, phase }: { title: string; phase: number | "1" }) {
  return (
    <Layout title={title}>
      <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-base-700 bg-base-900 py-24 text-center">
        <Construction className="mb-4 text-slate-600" size={32} strokeWidth={1.5} />
        <p className="text-sm font-medium text-slate-300">Ainda não implementado</p>
        <p className="mt-1 text-xs text-slate-500">
          Esta tela entra em produção na Fase {phase} do ROADMAP.md.
        </p>
      </div>
    </Layout>
  );
}
