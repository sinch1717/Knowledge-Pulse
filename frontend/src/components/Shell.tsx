import { NavLink, Outlet } from "react-router-dom";
import clsx from "clsx";
import { api, usingMockData } from "@/lib/api";
import { useEffect, useState } from "react";

const nav = [
  { to: "/", label: "This period", end: true },
  { to: "/insights", label: "Insights" },
  { to: "/report", label: "Report" },
  { to: "/ask", label: "Ask" },
  { to: "/sources", label: "Sources" },
  { to: "/evaluation", label: "Evaluation" },
];

export function Shell() {
  return (
    <div className="min-h-screen md:flex">
      <aside className="border-b border-rule bg-paper-sunk md:sticky md:top-0 md:h-screen md:w-60 md:shrink-0 md:border-b-0 md:border-r">
        <div className="flex items-baseline gap-2 px-6 pb-4 pt-6">
          <span className="font-display text-h3 font-semibold tracking-tight">Knowledge</span>
          <span className="font-display text-h3 text-oxblood">Pulse</span>
        </div>
        <p className="max-w-[15rem] px-6 pb-6 text-small text-ink-faint">
          Reads the support archive and ranks what customers are stuck on.
        </p>

        <nav className="flex gap-1 overflow-x-auto px-4 pb-4 md:flex-col md:gap-0 md:overflow-visible md:px-3">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                clsx(
                  "whitespace-nowrap rounded px-3 py-2 text-small transition-colors",
                  isActive
                    ? "bg-oxblood-wash font-medium text-oxblood-deep"
                    : "text-ink-soft hover:bg-paper hover:text-ink",
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        {usingMockData && (
          <div className="mx-6 mt-2 border-l-2 border-ochre pl-3 text-micro leading-relaxed text-ink-faint md:absolute md:bottom-6">
            Running on placeholder data. Set VITE_API_BASE_URL to connect the backend.
          </div>
        )}
      </aside>

      <main className="min-w-0 flex-1">
        <Outlet />
      </main>
    </div>
  );
}
