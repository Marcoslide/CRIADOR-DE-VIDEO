import { NavLink } from "react-router-dom";

import { NAV_ITEMS } from "../nav";

export function Sidebar() {
  return (
    <aside className="flex h-screen w-64 shrink-0 flex-col border-r border-base-700 bg-base-900">
      <div className="px-5 py-6">
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">
          Digital Human
        </p>
        <p className="text-lg font-semibold text-slate-50">Video Factory</p>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 pb-4">
        <ul className="space-y-0.5">
          {NAV_ITEMS.map((item) => (
            <li key={item.path}>
              <NavLink
                to={item.path}
                end={item.path === "/"}
                className={({ isActive }) =>
                  [
                    "group flex items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors",
                    isActive
                      ? "bg-base-800 text-slate-50"
                      : "text-slate-400 hover:bg-base-850 hover:text-slate-200",
                  ].join(" ")
                }
              >
                <span className="flex items-center gap-2.5">
                  <item.icon size={16} strokeWidth={1.75} />
                  {item.label}
                </span>
                {!item.implemented && (
                  <span className="rounded-full bg-base-700 px-1.5 py-0.5 text-[10px] font-medium text-slate-400">
                    Fase {item.phase}
                  </span>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="border-t border-base-700 px-5 py-4 text-[11px] text-slate-600">
        Hostinger GPU Node · RTX 5090
      </div>
    </aside>
  );
}
