import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Home from "./pages/Home";
import Projects from "./pages/Projects";
import ProjectDetail from "./pages/ProjectDetail";
import RunDetail from "./pages/RunDetail";
import Workflows from "./pages/Workflows";
import WorkflowLive from "./pages/WorkflowLive";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Home />} />
        <Route path="/projects" element={<Projects />} />
        <Route path="/projects/:id" element={<ProjectDetail />} />
        <Route path="/projects/:id/runs/:runId" element={<RunDetail />} />
        <Route path="/workflows" element={<Workflows />} />
        <Route path="/workflows/live" element={<WorkflowLive />} />
        <Route path="/workflows/live/:workflowId" element={<WorkflowLive />} />
      </Route>
    </Routes>
  );
}
