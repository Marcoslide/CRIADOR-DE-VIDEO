import { AlertTriangle, CheckCircle2, CircleSlash, Loader2 } from "lucide-react";

export type PillState =
  | "connected"
  | "error"
  | "timeout"
  | "not_configured"
  | "auth_expired"
  | "checking"
  | "connecting"
  | "degraded";

const STYLES: Record<PillState, { label: string; className: string; icon: React.ReactNode }> = {
  connected: {
    label: "Conectado",
    className: "bg-emerald-500/10 text-emerald-400 ring-emerald-500/30",
    icon: <CheckCircle2 size={14} />,
  },
  error: {
    label: "Erro",
    className: "bg-red-500/10 text-red-400 ring-red-500/30",
    icon: <AlertTriangle size={14} />,
  },
  timeout: {
    label: "Timeout",
    className: "bg-amber-500/10 text-amber-400 ring-amber-500/30",
    icon: <AlertTriangle size={14} />,
  },
  not_configured: {
    label: "Não configurado",
    className: "bg-slate-500/10 text-slate-400 ring-slate-500/30",
    icon: <CircleSlash size={14} />,
  },
  auth_expired: {
    label: "Autorização expirada",
    className: "bg-red-500/10 text-red-400 ring-red-500/30",
    icon: <AlertTriangle size={14} />,
  },
  checking: {
    label: "Verificando…",
    className: "bg-slate-500/10 text-slate-400 ring-slate-500/30",
    icon: <Loader2 size={14} className="animate-spin" />,
  },
  connecting: {
    label: "Conectando…",
    className: "bg-slate-500/10 text-slate-400 ring-slate-500/30",
    icon: <Loader2 size={14} className="animate-spin" />,
  },
  degraded: {
    label: "Degradado",
    className: "bg-amber-500/10 text-amber-400 ring-amber-500/30",
    icon: <AlertTriangle size={14} />,
  },
};

export function StatusPill({ state }: { state: PillState }) {
  const style = STYLES[state];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${style.className}`}
    >
      {style.icon}
      {style.label}
    </span>
  );
}
