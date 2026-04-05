import { Link, Outlet } from "react-router-dom";
import StatInkGrainFilter from "./StatInkGrainFilter";

export default function Layout() {
  return (
    <div className="min-h-screen flex flex-col bg-paper">
      <StatInkGrainFilter />
      <header className="border-b border-neutral-300/80 bg-paper/90 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <Link
            to="/"
            className="heading-main text-sm sm:text-base text-orange-600 hover:text-orange-500"
          >
            Midnight Agent Space
          </Link>
          <nav className="flex gap-6 text-xs sm:text-sm font-bold uppercase tracking-widest text-neutral-500">
            <Link to="/" className="hover:text-neutral-900 transition-colors">
              Dashboard
            </Link>
            <Link to="/projects" className="hover:text-neutral-900 transition-colors">
              Projects
            </Link>
            <Link to="/workflows" className="hover:text-neutral-900 transition-colors">
              Workflows
            </Link>
            <Link to="/workflows/live" className="hover:text-orange-600 transition-colors">
              Live
            </Link>
          </nav>
        </div>
      </header>
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-8">
        <Outlet />
      </main>
      <footer className="border-t border-neutral-200 py-4 text-center text-[10px] uppercase tracking-widest text-neutral-500">
        Local PostgreSQL · Temporal · Agent Space
      </footer>
    </div>
  );
}
