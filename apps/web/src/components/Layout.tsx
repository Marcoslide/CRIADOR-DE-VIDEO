import type { PropsWithChildren } from "react";

import { Sidebar } from "./Sidebar";

export function Layout({ title, children }: PropsWithChildren<{ title: string }>) {
  return (
    <div className="flex min-h-screen flex-col bg-base-950 md:flex-row">
      <Sidebar />
      <div className="min-w-0 flex-1 overflow-y-auto">
        <header className="border-b border-base-700 px-4 py-4 sm:px-8 sm:py-5">
          <h1 className="text-xl font-semibold text-slate-50">{title}</h1>
        </header>
        <main className="px-4 py-5 sm:px-8 sm:py-6">{children}</main>
      </div>
    </div>
  );
}
