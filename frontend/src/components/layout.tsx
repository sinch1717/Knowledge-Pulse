import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import clsx from "clsx";
import { ChevronDown } from "lucide-react";
import { usingMockData } from "@/lib/api";

const accountName = import.meta.env.VITE_ACCOUNT_NAME || "Sinchana";

export const features = [
  { to: "/", label: "This period", end: true },
  { to: "/insights", label: "Insights" },
  { to: "/report", label: "Report" },
  { to: "/ask", label: "Ask" },
  { to: "/sources", label: "Sources" },
  { to: "/evaluation", label: "Evaluation" },
];

const services = [
  { to: "/ask", label: "Assistant", note: "Answers customers from your own sources" },
  { to: "/insights", label: "Customer insights", note: "Ranks what customers are stuck on" },
  { to: "/report", label: "Client report", note: "Turns insights into actions for your team" },
  { to: "/sources", label: "Knowledge sources", note: "Websites and documents the assistant reads" },
];

/** A small popover menu that closes on outside click and Escape. */
function Menu({
  label,
  align = "right",
  children,
}: {
  label: ReactNode;
  align?: "left" | "right";
  children: (close: () => void) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={root} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="menu"
        className={clsx(
          "inline-flex items-center gap-1 rounded px-2.5 py-1.5 text-small transition-colors",
          open ? "bg-paper text-ink" : "text-ink-soft hover:bg-paper hover:text-ink",
        )}
      >
        {label}
        <ChevronDown size={14} className={clsx("transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <div
          role="menu"
          className={clsx(
            "absolute top-full z-40 mt-2 w-72 rounded-md border border-rule-strong bg-paper-raised py-2 shadow-[0_14px_36px_-20px_rgba(22,19,15,0.45)]",
            align === "right" ? "right-0" : "left-0",
          )}
        >
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}

export function PrimaryNavbar() {
  return (
    <div className="border-b border-rule bg-paper-sunk">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-5 md:px-10">
        <Link to="/" className="flex items-baseline gap-0.5" aria-label="KnowledgePulse home">
          <span className="font-display text-h3 font-semibold tracking-tight">Knowledge</span>
          <span className="font-display text-h3 text-oxblood">Pulse</span>
        </Link>

        <div className="flex items-center gap-1">
          <Menu label="Services">
            {(close) =>
              services.map((s) => (
                <Link
                  key={s.to}
                  to={s.to}
                  role="menuitem"
                  onClick={close}
                  className="block px-4 py-2 hover:bg-paper"
                >
                  <span className="block text-small font-medium text-ink">{s.label}</span>
                  <span className="block text-micro text-ink-faint">{s.note}</span>
                </Link>
              ))
            }
          </Menu>

          <Menu
            label={
              <span className="inline-flex items-center gap-2">
                <span
                  aria-hidden
                  className="grid h-6 w-6 place-items-center rounded-full bg-oxblood text-micro font-semibold text-paper-raised"
                >
                  {accountName.slice(0, 1).toUpperCase()}
                </span>
                <span className="hidden sm:inline">{accountName}</span>
              </span>
            }
          >
            {(close) => (
              <>
                <div className="border-b border-rule px-4 pb-3 pt-1">
                  <p className="text-small font-medium text-ink">{accountName}</p>
                  <p className="text-micro text-ink-faint">
                    {usingMockData ? "Viewing placeholder data" : "Connected to the KnowledgePulse API"}
                  </p>
                </div>
                <Link to="/sources" role="menuitem" onClick={close} className="block px-4 py-2 text-small hover:bg-paper">
                  Manage sources
                </Link>
                <Link to="/evaluation" role="menuitem" onClick={close} className="block px-4 py-2 text-small hover:bg-paper">
                  Assistant quality
                </Link>
              </>
            )}
          </Menu>
        </div>
      </div>
    </div>
  );
}

export function FeatureSubNav() {
  return (
    <nav aria-label="Sections" className="border-b border-rule bg-paper/95 backdrop-blur">
      <div className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-3 md:px-8">
        {features.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              clsx(
                "relative whitespace-nowrap px-3 py-3 text-small transition-colors",
                isActive
                  ? "font-medium text-oxblood-deep after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:bg-oxblood"
                  : "text-ink-soft hover:text-ink",
              )
            }
          >
            {item.label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}

export function MockDataNotice() {
  if (!usingMockData) return null;
  return (
    <div className="border-b border-rule bg-ochre-wash/60">
      <p className="mx-auto max-w-6xl px-5 py-1.5 text-micro text-[#7A5A17] md:px-10">
        Running on placeholder data. Set VITE_API_BASE_URL to connect the backend.
      </p>
    </div>
  );
}
