import { createBrowserRouter, Navigate } from "react-router-dom";

import { AdminLayout } from "../components/layout/AdminLayout.jsx";
import { BusinessProtectedRoute, CustomerProtectedRoute } from "../components/common/ProtectedRoute.jsx";
import { CustomerLayout } from "../components/layout/CustomerLayout.jsx";
import { DashboardLayout } from "../components/layout/DashboardLayout.jsx";
import { PublicLayout } from "../components/layout/PublicLayout.jsx";
import { PlaceholderPage } from "../components/common/PlaceholderPage.jsx";
import { NotFoundPage } from "../components/common/NotFoundPage.jsx";
import { AdminCategoriesPage } from "../features/admin/AdminCategoriesPage.jsx";
import { AdminModulesPage } from "../features/admin/AdminModulesPage.jsx";
import { AdminOverviewPage } from "../features/admin/AdminOverviewPage.jsx";
import { AdminPaymentsPage } from "../features/admin/AdminPaymentsPage.jsx";
import { AdminReportsPage } from "../features/admin/AdminReportsPage.jsx";
import { AdminTenantsPage } from "../features/admin/AdminTenantsPage.jsx";
import { AdminUsersPage } from "../features/admin/AdminUsersPage.jsx";
import { BusinessLogin } from "../features/auth/BusinessLogin.jsx";
import { BusinessRegister } from "../features/auth/BusinessRegister.jsx";
import { PhonePasswordResetPage } from "../features/auth/PhonePasswordResetPage.jsx";
import { CustomerLogin } from "../features/customer/CustomerLogin.jsx";
import { CustomerBusinessItemPage } from "../features/customer/CustomerBusinessItemPage.jsx";
import { CustomerBusinessChatPage } from "../features/customer/CustomerBusinessChatPage.jsx";
import { CustomerBusinessPage } from "../features/customer/CustomerBusinessPage.jsx";
import { CustomerCartPage } from "../features/customer/CustomerCartPage.jsx";
import { CustomerMarketplace } from "../features/customer/CustomerMarketplace.jsx";
import { CustomerNotificationsPage } from "../features/customer/CustomerNotificationsPage.jsx";
import { CustomerOrderDetailPage } from "../features/customer/CustomerOrderDetailPage.jsx";
import { CustomerOrdersPage } from "../features/customer/CustomerOrdersPage.jsx";
import { CustomerProfileSettings } from "../features/customer/CustomerProfileSettings.jsx";
import { CustomerRegister } from "../features/customer/CustomerRegister.jsx";
import { CustomerProfilePage } from "../features/customers/CustomerProfilePage.jsx";
import { CustomersPage } from "../features/customers/CustomersPage.jsx";
import { CustomFieldsPage } from "../features/custom-fields/CustomFieldsPage.jsx";
import { AnalyticsPage } from "../features/dashboard/AnalyticsPage.jsx";
import { AIConversationsPage } from "../features/dashboard/AIConversationsPage.jsx";
import { AgentToolsPage } from "../features/dashboard/AgentToolsPage.jsx";
import { DashboardHome } from "../features/dashboard/DashboardHome.jsx";
import { DeploymentReadinessPage } from "../features/dashboard/DeploymentReadinessPage.jsx";
import { FinalQAPage } from "../features/dashboard/FinalQAPage.jsx";
import { NotificationsPage } from "../features/dashboard/NotificationsPage.jsx";
import { OwnerAgentPage } from "../features/dashboard/OwnerAgentPage.jsx";
import { PaymentsPage } from "../features/dashboard/PaymentsPage.jsx";
import { ReportsPage } from "../features/dashboard/ReportsPage.jsx";
import { SubmissionCenterPage } from "../features/dashboard/SubmissionCenterPage.jsx";
import { KnowledgeBasePage } from "../features/dashboard/KnowledgeBasePage.jsx";
import { LaunchWizardPage } from "../features/dashboard/LaunchWizardPage.jsx";
import { TransactionsPage } from "../features/dashboard/TransactionsPage.jsx";
import { WhatsAppAgentPage } from "../features/dashboard/WhatsAppAgentPage.jsx";
import { WhatsAppConnectCallbackPage } from "../features/dashboard/WhatsAppConnectCallbackPage.jsx";
import { ItemDetailPage } from "../features/items/ItemDetailPage.jsx";
import { ItemImportPage } from "../features/items/ItemImportPage.jsx";
import { ItemsPage } from "../features/items/ItemsPage.jsx";
import { ModuleMarketplace } from "../features/modules/ModuleMarketplace.jsx";
import { LandingPage } from "../features/public/LandingPage.jsx";
import { PublicBusinessPage } from "../features/public/PublicBusinessPage.jsx";
import { PublicBusinessAboutPage } from "../features/public/PublicBusinessAboutPage.jsx";
import { PublicBusinessChatPage } from "../features/public/PublicBusinessChatPage.jsx";
import { PublicBusinessCatalogPage } from "../features/public/PublicBusinessCatalogPage.jsx";
import { PublicBusinessContactPage } from "../features/public/PublicBusinessContactPage.jsx";
import { PublicItemPage } from "../features/public/PublicItemPage.jsx";
import { PublicBusinessRequestPage } from "../features/public/PublicBusinessRequestPage.jsx";
import { PublicWebsiteSettings } from "../features/public-website/PublicWebsiteSettings.jsx";
import { BusinessProfile } from "../features/tenants/BusinessProfile.jsx";

export const router = createBrowserRouter([
  { path: "/login", element: <BusinessLogin /> },
  { path: "/register", element: <BusinessRegister /> },
  { path: "/forgot-password", element: <PhonePasswordResetPage /> },
  { path: "/customer/login", element: <CustomerLogin /> },
  { path: "/customer/register", element: <CustomerRegister /> },
  { path: "/customer/forgot-password", element: <PhonePasswordResetPage customer /> },
  {
    element: <PublicLayout />,
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
          { path: "whatsapp-agent/connect/callback", element: <WhatsAppConnectCallbackPage /> },
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
