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
import Bills from "@/pages/Bills";
import Notices from "@/pages/Notices";
import VoiceCampaigns from "@/pages/VoiceCampaigns";
import SmartReminders from "@/pages/SmartReminders";
import Conversations from "@/pages/Conversations";
import MessageLogs from "@/pages/MessageLogs";
import Calls from "@/pages/Calls";
import Reports from "@/pages/Reports";
import Providers from "@/pages/Providers";
import Webhooks from "@/pages/Webhooks";
import Team from "@/pages/Team";
import Companies from "@/pages/Companies";
import AuditLogs from "@/pages/AuditLogs";
import Invoices from "@/pages/Invoices";
import Settings from "@/pages/Settings";
import WhatsAppSettings from "@/pages/WhatsAppSettings";
import WhatsAppNumbers from "@/pages/WhatsAppNumbers";
import Wallet from "@/pages/Wallet";
import ForgotPassword from "@/pages/ForgotPassword";
import ResetPassword from "@/pages/ResetPassword";

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/contacts" element={<Contacts />} />
              <Route path="/contacts/:id" element={<ContactProfile />} />
              <Route path="/templates" element={<Templates />} />
              <Route path="/campaigns" element={<RoleRoute allow={["super_admin","admin"]}><Campaigns /></RoleRoute>} />
              <Route path="/campaigns/:id" element={<RoleRoute allow={["super_admin","admin"]}><CampaignDetail /></RoleRoute>} />
              <Route path="/lists" element={<RoleRoute allow={["super_admin","admin"]}><Lists /></RoleRoute>} />
              <Route path="/bills" element={<Bills />} />
              <Route path="/notices" element={<RoleRoute allow={["super_admin","admin"]}><Notices /></RoleRoute>} />
              <Route path="/voice-campaigns" element={<VoiceCampaigns />} />
              <Route path="/reminders" element={<RoleRoute allow={["super_admin","admin"]}><SmartReminders /></RoleRoute>} />
              <Route path="/conversations" element={<Conversations />} />
              <Route path="/messages" element={<MessageLogs />} />
              <Route path="/calls" element={<Calls />} />
              <Route path="/reports" element={<RoleRoute allow={["super_admin","admin"]}><Reports /></RoleRoute>} />
              <Route path="/providers" element={<RoleRoute allow={["super_admin","admin"]}><Providers /></RoleRoute>} />
              <Route path="/webhooks" element={<RoleRoute allow={["super_admin","admin"]}><Webhooks /></RoleRoute>} />
              <Route path="/team" element={<RoleRoute allow={["super_admin","admin"]}><Team /></RoleRoute>} />
              <Route path="/companies" element={<RoleRoute allow={["super_admin"]}><Companies /></RoleRoute>} />
              <Route path="/audit-logs" element={<RoleRoute allow={["super_admin","admin"]}><AuditLogs /></RoleRoute>} />
              <Route path="/invoices" element={<RoleRoute allow={["super_admin","admin"]}><Invoices /></RoleRoute>} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/whatsapp-settings" element={<RoleRoute allow={["super_admin","admin"]}><WhatsAppSettings /></RoleRoute>} />
              <Route path="/whatsapp-numbers" element={<RoleRoute allow={["super_admin","admin","manager","agent"]}><WhatsAppNumbers /></RoleRoute>} />
              <Route path="/wallet" element={<Wallet />} />
            </Route>
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}
