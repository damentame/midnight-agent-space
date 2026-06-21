import { Link } from "react-router-dom";
import SidebarSettings from "../components/SidebarSettings";

export default function Settings() {
  return (
    <div className="space-y-6">
      <div>
        <Link to="/" className="text-xs font-bold uppercase tracking-widest text-orange-600">
          Back to flow
        </Link>
      </div>
      <section className="glass max-w-3xl border-neutral-200 p-6">
        <p className="heading-sub mb-2">Settings</p>
        <h1 className="heading-main text-2xl">Runtime and integrations</h1>
        <p className="mt-3 text-sm text-neutral-600">
          Configure CLI runtime, model selection, reviewer provider, and Figma token. These apply across all projects.
        </p>
        <div className="mt-6">
          <SidebarSettings />
        </div>
      </section>
    </div>
  );
}
