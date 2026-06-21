import { NavLink } from "react-router-dom";
import { useSettings } from "../context/SettingsContext";
import { runtimeLabel } from "../lib/cliRuntime";
import { modelSelectionLabel } from "../lib/modelSettings";

const NAV_ITEMS = [
  { to: "/", label: "Flow", short: "F" },
  { to: "/projects", label: "Projects", short: "P" },
  { to: "/workflows", label: "Workflows", short: "W" },
] as const;

export default function CollapsibleSidebar() {
  const { collapsed, toggleCollapsed, cliRuntime, modelSelectionMode } = useSettings();

  return (
    <aside
      className={`sticky top-0 z-20 flex h-screen shrink-0 flex-col border-r border-neutral-200/90 bg-paper-bright/95 transition-[width] duration-200 ease-out ${
        collapsed ? "w-[3.25rem]" : "w-60"
      }`}
      aria-label="Main sidebar"
    >
      <div className={`flex items-center gap-2 border-b border-neutral-300/80 p-2 ${collapsed ? "justify-center" : "px-3"}`}>
        {!collapsed && (
          <NavLink to="/" className="min-w-0 flex-1 truncate text-xs font-bold uppercase tracking-widest text-orange-600 hover:text-orange-500">
            Midnight
          </NavLink>
        )}
        <button
          type="button"
          onClick={toggleCollapsed}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-neutral-300 bg-paper-bright text-neutral-600 hover:border-orange-300 hover:text-orange-700"
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
        >
          <span className="text-sm leading-none" aria-hidden>
            {collapsed ? "»" : "«"}
          </span>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto overflow-x-hidden">
        <nav className={`flex flex-col gap-1 p-2 ${collapsed ? "items-center" : ""}`}>
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              title={item.label}
              className={({ isActive }) =>
                collapsed
                  ? `flex h-9 w-9 items-center justify-center rounded-lg border text-xs font-bold ${
                      isActive
                        ? "border-orange-400 bg-orange-50 text-orange-800"
                        : "border-neutral-300 bg-paper-bright text-neutral-600 hover:border-orange-300"
                    }`
                  : `rounded-lg border px-3 py-2 text-xs font-bold uppercase tracking-widest ${
                      isActive
                        ? "border-orange-400 bg-orange-50 text-orange-800"
                        : "border-neutral-300 bg-paper-field text-neutral-700 hover:border-orange-300"
                    }`
              }
            >
              {collapsed ? item.short : item.label}
            </NavLink>
          ))}
        </nav>
      </div>

      <div className={`mt-auto space-y-2 border-t border-neutral-300/80 p-2 ${collapsed ? "text-center" : ""}`}>
        <NavLink
          to="/settings"
          title="Settings"
          className={({ isActive }) =>
            collapsed
              ? `inline-flex h-9 w-9 items-center justify-center rounded-lg border text-xs font-bold ${
                  isActive
                    ? "border-orange-400 bg-orange-50 text-orange-800"
                    : "border-neutral-300 bg-paper-bright text-neutral-600 hover:border-orange-300"
                }`
              : `block rounded-lg border px-3 py-2 text-xs font-bold uppercase tracking-widest ${
                  isActive
                    ? "border-orange-400 bg-orange-50 text-orange-800"
                    : "border-neutral-300 bg-paper-field text-neutral-700 hover:border-orange-300"
                }`
          }
        >
          {collapsed ? "⚙" : "Settings"}
        </NavLink>
        {collapsed ? (
          <span
            className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-orange-200 bg-orange-50 text-[10px] font-bold text-orange-700"
            title={runtimeLabel(cliRuntime)}
          >
            {cliRuntime === "claude-cli" ? "C" : "X"}
          </span>
        ) : (
          <p className="text-[10px] font-bold uppercase tracking-widest text-neutral-500">
            Runtime
            <span className="mt-0.5 block text-orange-700">
              {runtimeLabel(cliRuntime)} · {modelSelectionLabel(modelSelectionMode)}
            </span>
          </p>
        )}
      </div>
    </aside>
  );
}
