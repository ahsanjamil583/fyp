import { lazy } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";

import { AdminLayout } from "../components/layout/AdminLayout.jsx";
import { BusinessProtectedRoute, CustomerProtectedRoute } from "../components/common/ProtectedRoute.jsx";
import { CustomerLayout } from "../components/layout/CustomerLayout.jsx";
import { DashboardLayout } from "../components/layout/DashboardLayout.jsx";
import { MarketingLayout } from "../components/layout/MarketingLayout.jsx";
import { PlaceholderPage } from "../components/common/PlaceholderPage.jsx";
import { NotFoundPage } from "../components/common/NotFoundPage.jsx";

// Every page is code-split so the first paint no longer downloads the whole app.
// Layouts and guards above stay eager because they render immediately.
const AdminCategoriesPage = lazy(() => import("../features/admin/AdminCategoriesPage.jsx").then((m) => ({ default: m.AdminCategoriesPage })));
const AdminModulesPage = lazy(() => import("../features/admin/AdminModulesPage.jsx").then((m) => ({ default: m.AdminModulesPage })));
const AdminOverviewPage = lazy(() => import("../features/admin/AdminOverviewPage.jsx").then((m) => ({ default: m.AdminOverviewPage })));
const AdminPaymentsPage = lazy(() => import("../features/admin/AdminPaymentsPage.jsx").then((m) => ({ default: m.AdminPaymentsPage })));
const AdminReportsPage = lazy(() => import("../features/admin/AdminReportsPage.jsx").then((m) => ({ default: m.AdminReportsPage })));
const AdminTenantsPage = lazy(() => import("../features/admin/AdminTenantsPage.jsx").then((m) => ({ default: m.AdminTenantsPage })));
const AdminUsersPage = lazy(() => import("../features/admin/AdminUsersPage.jsx").then((m) => ({ default: m.AdminUsersPage })));
const BusinessLogin = lazy(() => import("../features/auth/BusinessLogin.jsx").then((m) => ({ default: m.BusinessLogin })));
const BusinessRegister = lazy(() => import("../features/auth/BusinessRegister.jsx").then((m) => ({ default: m.BusinessRegister })));
const ForcedPasswordResetPage = lazy(() => import("../features/auth/ForcedPasswordResetPage.jsx").then((m) => ({ default: m.ForcedPasswordResetPage })));
const PhonePasswordResetPage = lazy(() => import("../features/auth/PhonePasswordResetPage.jsx").then((m) => ({ default: m.PhonePasswordResetPage })));
const CustomerLogin = lazy(() => import("../features/customer/CustomerLogin.jsx").then((m) => ({ default: m.CustomerLogin })));
const CustomerBusinessItemPage = lazy(() => import("../features/customer/CustomerBusinessItemPage.jsx").then((m) => ({ default: m.CustomerBusinessItemPage })));
const CustomerBusinessChatPage = lazy(() => import("../features/customer/CustomerBusinessChatPage.jsx").then((m) => ({ default: m.CustomerBusinessChatPage })));
const CustomerBusinessPage = lazy(() => import("../features/customer/CustomerBusinessPage.jsx").then((m) => ({ default: m.CustomerBusinessPage })));
const CustomerCartPage = lazy(() => import("../features/customer/CustomerCartPage.jsx").then((m) => ({ default: m.CustomerCartPage })));
const CustomerMarketplace = lazy(() => import("../features/customer/CustomerMarketplace.jsx").then((m) => ({ default: m.CustomerMarketplace })));
const CustomerNotificationsPage = lazy(() => import("../features/customer/CustomerNotificationsPage.jsx").then((m) => ({ default: m.CustomerNotificationsPage })));
const CustomerOrderDetailPage = lazy(() => import("../features/customer/CustomerOrderDetailPage.jsx").then((m) => ({ default: m.CustomerOrderDetailPage })));
const CustomerOrdersPage = lazy(() => import("../features/customer/CustomerOrdersPage.jsx").then((m) => ({ default: m.CustomerOrdersPage })));
const CustomerProfileSettings = lazy(() => import("../features/customer/CustomerProfileSettings.jsx").then((m) => ({ default: m.CustomerProfileSettings })));
const CustomerRegister = lazy(() => import("../features/customer/CustomerRegister.jsx").then((m) => ({ default: m.CustomerRegister })));
const CustomerProfilePage = lazy(() => import("../features/customers/CustomerProfilePage.jsx").then((m) => ({ default: m.CustomerProfilePage })));
const CustomersPage = lazy(() => import("../features/customers/CustomersPage.jsx").then((m) => ({ default: m.CustomersPage })));
const CustomFieldsPage = lazy(() => import("../features/custom-fields/CustomFieldsPage.jsx").then((m) => ({ default: m.CustomFieldsPage })));
const AnalyticsPage = lazy(() => import("../features/dashboard/AnalyticsPage.jsx").then((m) => ({ default: m.AnalyticsPage })));
const AIConversationsPage = lazy(() => import("../features/dashboard/AIConversationsPage.jsx").then((m) => ({ default: m.AIConversationsPage })));
const AgentToolsPage = lazy(() => import("../features/dashboard/AgentToolsPage.jsx").then((m) => ({ default: m.AgentToolsPage })));
const DashboardHome = lazy(() => import("../features/dashboard/DashboardHome.jsx").then((m) => ({ default: m.DashboardHome })));
const DeploymentReadinessPage = lazy(() => import("../features/dashboard/DeploymentReadinessPage.jsx").then((m) => ({ default: m.DeploymentReadinessPage })));
const FinalQAPage = lazy(() => import("../features/dashboard/FinalQAPage.jsx").then((m) => ({ default: m.FinalQAPage })));
const NotificationsPage = lazy(() => import("../features/dashboard/NotificationsPage.jsx").then((m) => ({ default: m.NotificationsPage })));
const OwnerAgentPage = lazy(() => import("../features/dashboard/OwnerAgentPage.jsx").then((m) => ({ default: m.OwnerAgentPage })));
const PaymentsPage = lazy(() => import("../features/dashboard/PaymentsPage.jsx").then((m) => ({ default: m.PaymentsPage })));
const ReportsPage = lazy(() => import("../features/dashboard/ReportsPage.jsx").then((m) => ({ default: m.ReportsPage })));
const SubmissionCenterPage = lazy(() => import("../features/dashboard/SubmissionCenterPage.jsx").then((m) => ({ default: m.SubmissionCenterPage })));
const KnowledgeBasePage = lazy(() => import("../features/dashboard/KnowledgeBasePage.jsx").then((m) => ({ default: m.KnowledgeBasePage })));
const LaunchWizardPage = lazy(() => import("../features/dashboard/LaunchWizardPage.jsx").then((m) => ({ default: m.LaunchWizardPage })));
const TransactionsPage = lazy(() => import("../features/dashboard/TransactionsPage.jsx").then((m) => ({ default: m.TransactionsPage })));
const WhatsAppAgentPage = lazy(() => import("../features/dashboard/WhatsAppAgentPage.jsx").then((m) => ({ default: m.WhatsAppAgentPage })));
const ItemDetailPage = lazy(() => import("../features/items/ItemDetailPage.jsx").then((m) => ({ default: m.ItemDetailPage })));
const ItemImportPage = lazy(() => import("../features/items/ItemImportPage.jsx").then((m) => ({ default: m.ItemImportPage })));
const ItemsPage = lazy(() => import("../features/items/ItemsPage.jsx").then((m) => ({ default: m.ItemsPage })));
const ModuleMarketplace = lazy(() => import("../features/modules/ModuleMarketplace.jsx").then((m) => ({ default: m.ModuleMarketplace })));
const LandingPage = lazy(() => import("../features/public/LandingPage.jsx").then((m) => ({ default: m.LandingPage })));
const PublicBusinessPage = lazy(() => import("../features/public/PublicBusinessPage.jsx").then((m) => ({ default: m.PublicBusinessPage })));
const PublicBusinessAboutPage = lazy(() => import("../features/public/PublicBusinessAboutPage.jsx").then((m) => ({ default: m.PublicBusinessAboutPage })));
const PublicBusinessChatPage = lazy(() => import("../features/public/PublicBusinessChatPage.jsx").then((m) => ({ default: m.PublicBusinessChatPage })));
const PublicBusinessCatalogPage = lazy(() => import("../features/public/PublicBusinessCatalogPage.jsx").then((m) => ({ default: m.PublicBusinessCatalogPage })));
const PublicBusinessContactPage = lazy(() => import("../features/public/PublicBusinessContactPage.jsx").then((m) => ({ default: m.PublicBusinessContactPage })));
const PublicItemPage = lazy(() => import("../features/public/PublicItemPage.jsx").then((m) => ({ default: m.PublicItemPage })));
const PublicBusinessRequestPage = lazy(() => import("../features/public/PublicBusinessRequestPage.jsx").then((m) => ({ default: m.PublicBusinessRequestPage })));
const PublicWebsiteSettings = lazy(() => import("../features/public-website/PublicWebsiteSettings.jsx").then((m) => ({ default: m.PublicWebsiteSettings })));
const BusinessProfile = lazy(() => import("../features/tenants/BusinessProfile.jsx").then((m) => ({ default: m.BusinessProfile })));

export const router = createBrowserRouter([
  { path: "/login", element: <BusinessLogin /> },
  { path: "/register", element: <BusinessRegister /> },
  { path: "/forgot-password", element: <PhonePasswordResetPage /> },
  { path: "/update-password", element: <ForcedPasswordResetPage /> },
  { path: "/customer/login", element: <CustomerLogin /> },
  { path: "/customer/register", element: <CustomerRegister /> },
  { path: "/customer/forgot-password", element: <PhonePasswordResetPage customer /> },
  { path: "/customer/update-password", element: <ForcedPasswordResetPage customer /> },
  {
    element: <MarketingLayout />,
    children: [
      {
        path: "/",
        element: <LandingPage />,
      },
    ],
  },
  {
    path: "/businesses/:tenantSlug",
    element: <PublicBusinessPage />,
  },
  {
    path: "/businesses/:tenantSlug/items",
    element: <PublicBusinessCatalogPage />,
  },
  {
    path: "/businesses/:tenantSlug/services",
    element: <PublicBusinessCatalogPage />,
  },
  {
    path: "/businesses/:tenantSlug/about",
    element: <PublicBusinessAboutPage />,
  },
  {
    path: "/businesses/:tenantSlug/contact",
    element: <PublicBusinessContactPage />,
  },
  {
    path: "/businesses/:tenantSlug/request",
    element: <PublicBusinessRequestPage />,
  },
  {
    path: "/businesses/:tenantSlug/items/:itemId",
    element: <PublicItemPage />,
  },
  {
    path: "/businesses/:tenantSlug/chat",
    element: <PublicBusinessChatPage />,
  },
  {
    path: "/customer",
    element: <CustomerProtectedRoute />,
    children: [
      {
        element: <CustomerLayout />,
        children: [
          { index: true, element: <Navigate to="/customer/marketplace" replace /> },
          { path: "marketplace", element: <CustomerMarketplace /> },
          {
            path: "businesses/:tenantSlug",
            element: <CustomerBusinessPage />,
          },
          {
            path: "businesses/:tenantSlug/items",
            element: <CustomerBusinessPage />,
          },
          {
            path: "businesses/:tenantSlug/items/:itemId",
            element: <CustomerBusinessItemPage />,
          },
          {
            path: "businesses/:tenantSlug/chat",
            element: <CustomerBusinessChatPage />,
          },
          { path: "cart", element: <CustomerCartPage /> },
          { path: "orders", element: <CustomerOrdersPage /> },
          { path: "orders/:orderId", element: <CustomerOrderDetailPage /> },
          { path: "profile", element: <CustomerProfileSettings /> },
          { path: "notifications", element: <CustomerNotificationsPage /> },
        ],
      },
    ],
  },
  {
    path: "/dashboard",
    element: <BusinessProtectedRoute />,
    children: [
      {
        element: <DashboardLayout />,
        children: [
          { index: true, element: <DashboardHome /> },
          { path: "business", element: <BusinessProfile /> },
          { path: "launch-wizard", element: <LaunchWizardPage /> },
          { path: "modules", element: <ModuleMarketplace /> },
          { path: "custom-fields", element: <CustomFieldsPage /> },
          { path: "transactions", element: <TransactionsPage /> },
          { path: "customers", element: <CustomersPage /> },
          { path: "customers/:customerId", element: <CustomerProfilePage /> },
          { path: "items", element: <ItemsPage /> },
          { path: "items/import", element: <ItemImportPage /> },
          { path: "items/:itemId", element: <ItemDetailPage /> },
          { path: "public-website", element: <PublicWebsiteSettings /> },
          { path: "analytics", element: <AnalyticsPage /> },
          { path: "ai-conversations", element: <AIConversationsPage /> },
          { path: "knowledge-base", element: <KnowledgeBasePage /> },
          { path: "agent-tools", element: <AgentToolsPage /> },
          { path: "owner-agent", element: <OwnerAgentPage /> },
          { path: "whatsapp-agent", element: <WhatsAppAgentPage /> },
          { path: "payments", element: <PaymentsPage /> },
          { path: "reports", element: <ReportsPage /> },
          { path: "notifications", element: <NotificationsPage /> },
          { path: "deployment-readiness", element: <DeploymentReadinessPage /> },
          { path: "final-qa", element: <FinalQAPage /> },
          { path: "submission-center", element: <SubmissionCenterPage /> },
        ],
      },
    ],
  },
  {
    path: "/admin",
    element: <BusinessProtectedRoute adminOnly />,
    children: [
      {
        element: <AdminLayout />,
        children: [
          { index: true, element: <AdminOverviewPage /> },
          { path: "users", element: <AdminUsersPage /> },
          { path: "tenants", element: <AdminTenantsPage /> },
          { path: "business-categories", element: <AdminCategoriesPage /> },
          { path: "modules", element: <AdminModulesPage /> },
          { path: "payments", element: <AdminPaymentsPage /> },
          { path: "reports", element: <AdminReportsPage /> },
          { path: "notifications", element: <PlaceholderPage title="Notifications" area="Admin" /> },
        ],
      },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
]);
