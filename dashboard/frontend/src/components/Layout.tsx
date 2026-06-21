import { Outlet, useLocation } from "react-router-dom";
import StatInkGrainFilter from "./StatInkGrainFilter";
import CollapsibleSidebar from "./CollapsibleSidebar";
import { SettingsProvider } from "../context/SettingsContext";

export default function Layout() {
  const location = useLocation();
  const isWidePage = /^\/projects\/\d+/.test(location.pathname);

  return (
    <SettingsProvider>
      <div className="min-h-screen flex">
        <StatInkGrainFilter />
        <CollapsibleSidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <main
            className={`mx-auto w-full flex-1 px-6 py-8 ${isWidePage ? "max-w-[1600px]" : "max-w-6xl"}`}
          >
            <Outlet />
          </main>
        </div>
      </div>
    </SettingsProvider>
  );
}
