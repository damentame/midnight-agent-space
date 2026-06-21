import { Navigate, Route, Routes, useParams } from "react-router-dom";
import Layout from "./components/Layout";
import Home from "./pages/Home";
import Projects from "./pages/Projects";
import ProjectDetail from "./pages/ProjectDetail";
import RunDetail from "./pages/RunDetail";
import RunTaskDetail from "./pages/RunTaskDetail";
import Settings from "./pages/Settings";
import Workflows from "./pages/Workflows";
import WorkflowLive from "./pages/WorkflowLive";

function ProjectTabRedirect() {
  const { id } = useParams();
  return <Navigate to={`/projects/${id}/context`} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Home />} />
        <Route path="/projects" element={<Projects />} />
        <Route path="/projects/:id/runs/:runId/tasks/:taskId" element={<RunTaskDetail />} />
        <Route path="/projects/:id/runs/:runId" element={<RunDetail />} />
        <Route path="/projects/:id/:tab" element={<ProjectDetail />} />
        <Route path="/projects/:id" element={<ProjectTabRedirect />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/workflows" element={<Workflows />} />
        <Route path="/workflows/live" element={<WorkflowLive />} />
        <Route path="/workflows/live/:workflowId" element={<WorkflowLive />} />
      </Route>
    </Routes>
  );
}
