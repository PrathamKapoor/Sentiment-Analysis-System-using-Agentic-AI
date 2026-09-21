import { Routes, Route, Navigate } from "react-router-dom";
import AuthLayout from "./layouts/AuthLayout";
import AppLayout from "./layouts/AppLayout";
import ProjectWorkspaceLayout from "./layouts/ProjectWorkspaceLayout";
import ProtectedRoute from "./routes/ProtectedRoute";
import RoleGuard from "./routes/RoleGuard";

import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import ProjectManagement from "./pages/ProjectManagement";
import ProjectDetails from "./pages/ProjectDetails";
import DataSourceManagement from "./pages/DataSourceManagement";
import DatasetManagement from "./pages/DatasetManagement";
import ReviewManagement from "./pages/ReviewManagement";
import SentimentAnalysisResults from "./pages/SentimentAnalysisResults";
import TopicAnalysis from "./pages/TopicAnalysis";
import KeywordAndWordCloud from "./pages/KeywordAndWordCloud";
import SentimentTrends from "./pages/SentimentTrends";
import AspectAndRecommendations from "./pages/AspectAndRecommendations";
import ProductComparison from "./pages/ProductComparison";
import AiSummaryPage from "./pages/AiSummaryPage";
import AlertManagement from "./pages/AlertManagement";
import ReportsPage from "./pages/ReportsPage";
import UserManagement from "./pages/UserManagement";
import OrganisationRoleManagement from "./pages/OrganisationRoleManagement";
import SentimentModelQuality from "./pages/SentimentModelQuality";
import AccessDenied from "./pages/AccessDenied";
import NotFound from "./pages/NotFound";

const ADMIN_ROLES = ["Organisation Owner", "Organisation Administrator"];

export default function App() {
  return (
    <Routes>
      <Route element={<AuthLayout />}>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
      </Route>

      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/projects" element={<ProjectManagement />} />
          <Route path="/projects/:projectId" element={<ProjectWorkspaceLayout />}>
            <Route index element={<ProjectDetails />} />
            <Route path="sources" element={<DataSourceManagement />} />
            <Route path="datasets" element={<DatasetManagement />} />
            <Route path="reviews" element={<ReviewManagement />} />
            <Route path="analysis/sentiment" element={<SentimentAnalysisResults />} />
            <Route path="analysis/topics" element={<TopicAnalysis />} />
            <Route path="analysis/keywords" element={<KeywordAndWordCloud />} />
            <Route path="analysis/trends" element={<SentimentTrends />} />
            <Route path="analysis/aspects" element={<AspectAndRecommendations />} />
            <Route path="ai-summary" element={<AiSummaryPage />} />
            <Route path="alerts" element={<AlertManagement />} />
            <Route path="reports" element={<ReportsPage />} />
          </Route>
          <Route path="/comparison" element={<ProductComparison />} />
          <Route path="/evaluation" element={<SentimentModelQuality />} />

          <Route element={<RoleGuard allowedRoles={ADMIN_ROLES} />}>
            <Route path="/admin/users" element={<UserManagement />} />
            <Route path="/admin/organisation" element={<OrganisationRoleManagement />} />
          </Route>

          <Route path="/access-denied" element={<AccessDenied />} />
        </Route>
      </Route>

      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
