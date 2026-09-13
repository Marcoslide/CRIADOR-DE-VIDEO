/** Comparação lado a lado (seção 30). Nesta V1 só existe Reference Master vs. imagem de
 * ângulo — "Reference vs. Mesh render" é um contrato futuro (sem mesh real ainda), mas o
 * componente já aceita qualquer par de URLs, então plugar isso depois é só passar outra
 * URL, sem mudar este componente. */

interface Frame {
  label: string;
  url: string | null;
}

export function SideBySideCompare({ left, right }: { left: Frame; right: Frame }) {
  return (
    <div className="grid grid-cols-2 gap-3">
      {[left, right].map((frame) => (
        <div key={frame.label} className="rounded-lg border border-base-700 bg-base-950">
          <div className="flex aspect-square items-center justify-center overflow-hidden rounded-t-lg bg-base-900">
            {frame.url ? (
              <img src={frame.url} alt={frame.label} className="h-full w-full object-cover" />
            ) : (
              <span className="text-xs text-slate-600">sem imagem</span>
            )}
          </div>
          <p className="truncate px-2 py-1.5 text-center text-[11px] text-slate-500">{frame.label}</p>
        </div>
      ))}
    </div>
  );
}
