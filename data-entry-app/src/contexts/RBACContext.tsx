import React, { createContext, useContext, useMemo } from 'react';
import { useAuth } from './AuthContext';
import type { UserRole } from '../lib/supabase';
import { ROLE_PERMISSIONS, ROLES, hasPermission as checkPermission, canDelete, canWrite, canCreate, canUpdate, canExport, canView, isReadOnly } from '../constants/roles';

interface RBACContextType {
  // Role checks
  isAdmin: boolean;
  isEditor: boolean;
  isViewer: boolean;
  
  // Permission checks
  hasPermission: (permission: string) => boolean;
  canDelete: () => boolean;
  canWrite: () => boolean;
  canCreate: () => boolean;
  canUpdate: () => boolean;
  canExport: () => boolean;
  canView: () => boolean;
  isReadOnly: () => boolean;
  
  // User info
  userRole: UserRole | null;
  userPermissions: string[];
}

const RBACContext = createContext<RBACContextType | undefined>(undefined);

export const useRBAC = () => {
  const context = useContext(RBACContext);
  if (context === undefined) {
    throw new Error('useRBAC must be used within an RBACProvider');
  }
  return context;
};

interface RBACProviderProps {
  children: React.ReactNode;
}

export const RBACProvider: React.FC<RBACProviderProps> = ({ children }) => {
  const { user } = useAuth();

  const rbacValue = useMemo(() => {
    const userRole: UserRole | null = user?.role || null;
    const userPermissions: string[] = userRole ? ROLE_PERMISSIONS[userRole] || [] : [];

    return {
      isAdmin: userRole === ROLES.ADMIN,
      isEditor: userRole === ROLES.EDITOR,
      isViewer: userRole === ROLES.VIEWER,
      hasPermission: (permission: string) => {
        if (!userRole) return false;
        return checkPermission(userRole, permission);
      },
      canDelete: () => {
        if (!userRole) return false;
        return canDelete(userRole);
      },
      canWrite: () => {
        if (!userRole) return false;
        return canWrite(userRole);
      },
      canCreate: () => {
        if (!userRole) return false;
        return canCreate(userRole);
      },
      canUpdate: () => {
        if (!userRole) return false;
        return canUpdate(userRole);
      },
      canExport: () => {
        if (!userRole) return false;
        return canExport(userRole);
      },
      canView: () => {
        if (!userRole) return false;
        return canView(userRole);
      },
      isReadOnly: () => {
        if (!userRole) return false;
        return isReadOnly(userRole);
      },
      userRole,
      userPermissions,
    };
  }, [user]);

  return (
    <RBACContext.Provider value={rbacValue}>
      {children}
    </RBACContext.Provider>
  );
};
