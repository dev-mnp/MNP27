import React, { useState, useEffect } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { SettingsProvider } from './contexts/SettingsContext';
import { RBACProvider } from './contexts/RBACContext';
import { NotificationProvider } from './contexts/NotificationContext';
import Login from './components/Login';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import Dashboard from './components/Dashboard';
import ProtectedRoute from './components/ProtectedRoute';
import MasterEntry from './components/MasterEntry';
import ArticleManagement from './components/ArticleManagement';
import InventoryManagement from './components/InventoryManagement';
import UserManagement from './components/UserManagement';
import Profile from './components/Profile';
import AuditLogs from './components/AuditLogs';
import FundRequest from './components/FundRequest';
import FundRequestForm from './components/FundRequestForm';
import Phase2HallStageSplit from './components/Phase2HallStageSplit';
import Phase2SequenceList from './components/Phase2SequenceList';
import Phase2TokenModule from './components/Phase2TokenModule';

// AppLayout component for authenticated routes
const AppLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const location = useLocation();
  const [isSidebarMobileOpen, setIsSidebarMobileOpen] = useState(false);

  const toggleMobileSidebar = () => {
    setIsSidebarMobileOpen(!isSidebarMobileOpen);
  };

  // Close mobile sidebar when route changes
  useEffect(() => {
    setIsSidebarMobileOpen(false);
  }, [location.pathname]);

  // Close mobile sidebar on desktop
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth >= 768) {
        setIsSidebarMobileOpen(false);
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return (
    <div className="flex h-screen bg-gray-50 dark:bg-gray-900 overflow-hidden">
      {/* Mobile sidebar overlay */}
      {isSidebarMobileOpen && (
        <div 
          className="fixed inset-0 bg-black bg-opacity-50 z-40 md:hidden"
          onClick={() => setIsSidebarMobileOpen(false)}
        />
      )}
      
      {/* Sidebar with mobile classes */}
      <div className={`
        ${isSidebarMobileOpen ? 'translate-x-0' : '-translate-x-full'} 
        md:translate-x-0 fixed md:relative z-50 md:z-auto
        transition-transform duration-300 ease-in-out
        h-full
      `}>
        <Sidebar 
          isMobileOpen={isSidebarMobileOpen}
          onMobileClose={() => setIsSidebarMobileOpen(false)}
        />
      </div>
      
      <div className="flex-1 flex flex-col min-w-0">
        <Header 
          onToggleMobileSidebar={toggleMobileSidebar}
        />
        <main className="flex-1 overflow-auto bg-gray-50 dark:bg-gray-900 min-h-0">
          {children}
        </main>
      </div>
    </div>
  );
};

const AppContent: React.FC = () => {
  const { isAuthenticated } = useAuth();

  return (
    <Routes>
      {/* Public routes */}
      <Route 
        path="/login" 
        element={!isAuthenticated ? <Login /> : <Navigate to="/dashboard" replace />} 
      />
      
      {/* Protected routes */}
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <AppLayout>
              <Routes>
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/master-entry" element={<MasterEntry />} />
                <Route path="/article-management" element={<ArticleManagement />} />
                <Route path="/inventory-management" element={<InventoryManagement />} />
                <Route path="/fund-request" element={<FundRequest />} />
                <Route path="/fund-request/new" element={<FundRequestForm />} />
                <Route path="/fund-request/edit/:id" element={<FundRequestForm />} />
                <Route path="/seat-allocation" element={<Phase2HallStageSplit />} />
                <Route path="/sequence-list" element={<Phase2SequenceList />} />
                <Route path="/token-module" element={<Phase2TokenModule />} />
                <Route path="/user-management" element={<UserManagement />} />
                <Route path="/profile" element={<Profile />} />
                <Route path="/audit-logs" element={<AuditLogs />} />
                <Route path="*" element={<Navigate to="/dashboard" replace />} />
              </Routes>
            </AppLayout>
          </ProtectedRoute>
        }
      />
    </Routes>
  );
};

function App() {
  return (
    <AuthProvider>
      <SettingsProvider>
        <RBACProvider>
          <NotificationProvider>
          <AppContent />
          </NotificationProvider>
        </RBACProvider>
      </SettingsProvider>
    </AuthProvider>
  );
}

export default App;
