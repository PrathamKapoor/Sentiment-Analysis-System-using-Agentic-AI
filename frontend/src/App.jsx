import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import AuthLayout from "./layouts/AuthLayout";
import AppLayout from "./layouts/AppLayout";
import ProjectWorkspaceLayout from "./layouts/ProjectWorkspaceLayout";
import ProtectedRoute from "./routes/ProtectedRoute";
import RoleGuard from "./routes/RoleGuard";

const Login = lazy(() => import("./pages/Login"));
const Register = lazy(() => import("./pages/Register"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const ProjectManagement = lazy(() => import("./pages/ProjectManagement"));
const ProjectDetails = lazy(() => import("./pages/ProjectDetails"));
const DataSourceManagement = lazy(() => import("./pages/DataSourceManagement"));
const DatasetManagement = lazy(() => import("./pages/DatasetManagement"));
const ReviewManagement = lazy(() => import("./pages/ReviewManagement"));
const SentimentAnalysisResults = lazy(() => import("./pages/SentimentAnalysisResults"));
const TopicAnalysis = lazy(() => import("./pages/TopicAnalysis"));
const KeywordAndWordCloud = lazy(() => import("./pages/KeywordAndWordCloud"));
const SentimentTrends = lazy(() => import("./pages/SentimentTrends"));
const AspectAndRecommendations = lazy(() => import("./pages/AspectAndRecommendations"));
const ProductComparison = lazy(() => import("./pages/ProductComparison"));
const AiSummaryPage = lazy(() => import("./pages/AiSummaryPage"));
const AlertManagement = lazy(() => import("./pages/AlertManagement"));
const ReportsPage = lazy(() => import("./pages/ReportsPage"));
const UserManagement = lazy(() => import("./pages/UserManagement"));
const OrganisationRoleManagement = lazy(() => import("./pages/OrganisationRoleManagement"));
const SentimentModelQuality = lazy(() => import("./pages/SentimentModelQuality"));
const InvestigationWorkspace = lazy(() => import("./pages/InvestigationWorkspace"));
const AccessDenied = lazy(() => import("./pages/AccessDenied"));
const NotFound = lazy(() => import("./pages/NotFound"));

const ADMIN_ROLES = ["Organisation Owner", "Organisation Administrator"];

export default function App() {
  return (
    <Suspense
      fallback={<div className="container py-4" role="status" aria-live="polite">Loading page…</div>}
    >
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
              <Route path="investigations" element={<InvestigationWorkspace />} />
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
    </Suspense>
  );
}
