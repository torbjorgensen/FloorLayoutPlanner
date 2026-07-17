import {BrowserRouter, Navigate, Route, Routes, useParams} from "react-router-dom";

import PlannerPage from "./pages/PlannerPage";
import ProjectEditorPage from "./pages/ProjectEditorPage";
import ProjectsPage from "./pages/ProjectsPage";

function ProjectPlannerRoute() {
    const {projectId} = useParams();
    return projectId ? <PlannerPage projectId={projectId} /> : <Navigate replace to="/" />;
}

function App() {
    return (
        <BrowserRouter
            future={{v7_relativeSplatPath: true, v7_startTransition: true}}
        >
            <Routes>
                <Route element={<ProjectsPage />} path="/" />
                <Route element={<ProjectEditorPage />} path="/projects/:projectId/edit" />
                <Route element={<ProjectPlannerRoute />} path="/projects/:projectId" />
                <Route element={<Navigate replace to="/" />} path="*" />
            </Routes>
        </BrowserRouter>
    );
}

export default App;
