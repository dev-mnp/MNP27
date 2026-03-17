import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { 
  Sidebar as ProSidebar, 
  Menu, 
  MenuItem, 
  sidebarClasses
} from 'react-pro-sidebar';
import { 
  LayoutDashboard,
  ChevronLeft,
  ChevronRight,
  FileText,
  Package,
  Warehouse,
  Users,
  ClipboardList,
  DollarSign,
  CalendarCheck2,
  ListOrdered,
} from 'lucide-react';
import { useRBAC } from '../contexts/RBACContext';

interface SidebarProps {
  isMobileOpen?: boolean;
  onMobileClose?: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({ 
  isMobileOpen: _isMobileOpen = false,
  onMobileClose 
}) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { isAdmin } = useRBAC();
  const [collapsed, setCollapsed] = useState(false);

  const handleMenuItemClick = (path: string) => {
    navigate(path);
    if (onMobileClose && window.innerWidth < 768) {
      onMobileClose();
    }
  };

  const phase1Items = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, path: '/dashboard' },
    { id: 'master-entry', label: 'Master Entry', icon: FileText, path: '/master-entry' },
    { id: 'article-management', label: 'Article Management', icon: Package, path: '/article-management' },
    { id: 'inventory-management', label: 'Order Management', icon: Warehouse, path: '/inventory-management' },
    { id: 'fund-request', label: 'Fund Request', icon: DollarSign, path: '/fund-request' },
  ];

  const phase2Items = [
    { id: 'seat-allocation', label: 'Seat Allocation', icon: CalendarCheck2, path: '/seat-allocation' },
    { id: 'sequence-list', label: 'Sequence List', icon: ListOrdered, path: '/sequence-list' },
    // Hidden for now; keep route/components in codebase for later rollout.
    // { id: 'token-module', label: 'Tokens', icon: Ticket, path: '/token-module' },
  ];

  const adminItems = isAdmin
    ? [
        { id: 'user-management', label: 'User Management', icon: Users, path: '/user-management' },
        { id: 'audit-logs', label: 'Audit Logs', icon: ClipboardList, path: '/audit-logs' },
      ]
    : [];

  const toggleSidebar = () => {
    setCollapsed(!collapsed);
  };

  return (
    <div className="h-screen flex">
      <ProSidebar
        collapsed={collapsed}
        width="280px"
        collapsedWidth="80px"
        backgroundColor="var(--bg-primary)"
        rootStyles={{
          [`.${sidebarClasses.container}`]: {
            backgroundColor: 'var(--bg-primary)',
            borderRight: '1px solid var(--border-color)',
            boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.1)',
            height: '100vh',
          },
        }}
      >
        <div className="md:hidden absolute top-4 right-4 z-50">
          <button
            onClick={onMobileClose}
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            aria-label="Close sidebar"
          >
            <ChevronLeft className="w-5 h-5 text-gray-600 dark:text-gray-400" />
          </button>
        </div>

        <div className="flex flex-col h-full pt-10 md:pt-0">
          {/* Header with Logo and Toggle */}
          <div className="px-4 py-2 border-b border-gray-200 dark:border-gray-700 h-[59px] flex items-center relative">
            <div className="flex items-center w-full h-full">
              <div className={`flex items-center h-full ${collapsed ? 'flex-1 justify-between' : 'flex-1 min-w-0'}`}>
                {!collapsed && (
                  <div className="h-full flex items-center min-w-0">
                    <h2 className="text-lg font-bold text-gray-900 dark:text-white">Data Entry</h2>
                  </div>
                )}
                
                <button
                  onClick={toggleSidebar}
                  className={`hidden md:flex flex-shrink-0 transition-colors ${
                    collapsed 
                      ? 'p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700' 
                      : 'p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 ml-auto'
                  }`}
                  aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
                >
                  {collapsed ? (
                    <ChevronRight className="w-3 h-3 text-gray-600 dark:text-gray-400" />
                  ) : (
                    <ChevronLeft className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                  )}
                </button>
              </div>
            </div>
          </div>

          {/* Navigation Menu */}
          <div className="flex-1 py-4 overflow-y-auto">
            {[
              { key: 'phase1', items: phase1Items },
              { key: 'phase2', items: phase2Items },
              { key: 'admin', items: adminItems },
            ]
              .filter((section) => section.items.length > 0)
              .map((section, sectionIndex, sections) => (
                <div key={section.key} className="mb-2">
                  <Menu
                    menuItemStyles={{
                      button: ({ level, active }) => {
                        if (level === 0) {
                          return {
                            color: active ? '#ffffff' : 'var(--text-primary)',
                            backgroundColor: active ? '#3b82f6' : 'transparent',
                            margin: collapsed ? '0 8px' : '0 16px',
                            borderRadius: '8px',
                            padding: collapsed ? '12px' : '12px 16px',
                            justifyContent: collapsed ? 'center' : 'flex-start',
                            fontWeight: active ? '600' : '500',
                            fontSize: '14px',
                            '&:hover': {
                              backgroundColor: active ? '#2563eb' : 'var(--bg-tertiary)',
                              color: active ? '#ffffff' : 'var(--text-primary)',
                            },
                          };
                        }
                      },
                      icon: ({ active }) => ({
                        color: active ? '#ffffff' : 'var(--text-secondary)',
                        marginRight: collapsed ? '0' : '12px',
                        width: '20px',
                        height: '20px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }),
                      label: ({ active }) => ({
                        fontWeight: '500',
                        color: active ? '#ffffff' : 'var(--text-primary)',
                      }),
                    }}
                  >
                    {section.items.map((item) => {
                      const Icon = item.icon;
                      const isActive = location.pathname === item.path || location.pathname.startsWith(item.path + '/');

                      return (
                        <div
                          key={item.id}
                          className={`relative ${collapsed ? 'group' : ''}`}
                          title={collapsed ? item.label : ''}
                        >
                          <MenuItem icon={<Icon className="w-5 h-5" />} active={isActive} onClick={() => handleMenuItemClick(item.path)}>
                            {!collapsed && item.label}
                          </MenuItem>
                          {collapsed && (
                            <div className="absolute left-full ml-2 px-3 py-2 bg-gray-900 dark:bg-gray-700 text-white dark:text-gray-100 text-sm rounded-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 pointer-events-none z-50 whitespace-nowrap">
                              {item.label}
                              <div className="absolute right-full top-1/2 transform -translate-y-1/2 border-4 border-transparent border-r-gray-900 dark:border-r-gray-700"></div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </Menu>
                  {sectionIndex < sections.length - 1 && (
                    <div className={`mt-2 border-b border-gray-200 dark:border-gray-700 ${collapsed ? 'mx-3' : 'mx-4'}`} />
                  )}
                </div>
              ))}
          </div>
        </div>
      </ProSidebar>
    </div>
  );
};

export default Sidebar;
