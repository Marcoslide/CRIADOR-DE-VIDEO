import type { PropsWithChildren } from "react";

import { Sidebar } from "./Sidebar";

export function Layout({ title, children }: PropsWithChildren<{ title: string }>) {
  return (
    <div className="flex min-h-screen bg-base-950">
      <Sidebar />
      <div className="flex-1 overflow-y-auto">
        <header className="border-b border-base-700 px-8 py-5">
          <h1 className="text-xl font-semibold text-slate-50">{title}</h1>
        </header>
        <main className="px-8 py-6">{children}</main>
      </div>
    </div>
  );
}
