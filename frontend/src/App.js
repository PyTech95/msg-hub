import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import RoleRoute from "@/components/RoleRoute";
import AppLayout from "@/components/AppLayout";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Contacts from "@/pages/Contacts";
import ContactProfile from "@/pages/ContactProfile";
import Templates from "@/pages/Templates";
import Campaigns from "@/pages/Campaigns";
import CampaignDetail from "@/pages/CampaignDetail";
import Lists from "@/pages/Lists";
import Conversations from "@/pages/Conversations";
import MessageLogs from "@/pages/MessageLogs";
import Calls from "@/pages/Calls";
import Reports from "@/pages/Reports";
import Providers from "@/pages/Providers";
import Webhooks from "@/pages/Webhooks";
import Team from "@/pages/Team";
import Settings from "@/pages/Settings";

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/contacts" element={<Contacts />} />
              <Route path="/contacts/:id" element={<ContactProfile />} />
              <Route path="/templates" element={<Templates />} />
              <Route path="/campaigns" element={<RoleRoute allow={["super_admin","admin"]}><Campaigns /></RoleRoute>} />
              <Route path="/campaigns/:id" element={<RoleRoute allow={["super_admin","admin"]}><CampaignDetail /></RoleRoute>} />
              <Route path="/lists" element={<RoleRoute allow={["super_admin","admin"]}><Lists /></RoleRoute>} />
              <Route path="/conversations" element={<Conversations />} />
              <Route path="/messages" element={<MessageLogs />} />
              <Route path="/calls" element={<Calls />} />
              <Route path="/reports" element={<RoleRoute allow={["super_admin","admin"]}><Reports /></RoleRoute>} />
              <Route path="/providers" element={<RoleRoute allow={["super_admin","admin"]}><Providers /></RoleRoute>} />
              <Route path="/webhooks" element={<RoleRoute allow={["super_admin","admin"]}><Webhooks /></RoleRoute>} />
              <Route path="/team" element={<RoleRoute allow={["super_admin"]}><Team /></RoleRoute>} />
              <Route path="/settings" element={<Settings />} />
            </Route>
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}
