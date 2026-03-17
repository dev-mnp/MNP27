import { supabase } from '../lib/supabase';

export type ActionType = 'CREATE' | 'UPDATE' | 'DELETE' | 'LOGIN' | 'LOGOUT' | 'EXPORT' | 'STATUS_CHANGE';
export type EntityType = 'article' | 'master_entry' | 'order' | 'user' | 'district_beneficiary' | 'public_beneficiary' | 'institution_beneficiary' | 'system' | 'fund_request';

export interface AuditLog {
  id: string;
  user_id: string | null;
  action_type: ActionType;
  entity_type: EntityType;
  entity_id: string | null;
  details: Record<string, any>;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
}

export interface AuditLogWithUser extends AuditLog {
  app_users?: {
    name: string;
    email: string;
    role: string;
  };
}

export interface AuditLogFilters {
  userId?: string;
  actionType?: ActionType;
  entityType?: EntityType;
  entityId?: string;
  startDate?: string;
  endDate?: string;
  limit?: number;
  offset?: number;
}

/**
 * Get client IP address and user agent
 */
const getClientInfo = () => {
  // In a browser environment, we can't get the real IP address
  // This would need to be handled server-side for production
  return {
    ip_address: null,
    user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : null,
  };
};

export interface AuditLogDetails {
  // Common fields
  entity_name?: string; // Human-readable name of the entity (e.g., article name, user email)
  entity_summary?: string; // Brief summary of the entity
  
  // For CREATE and UPDATE actions
  new_values?: Record<string, any>; // All values of the newly created/updated entity
  
  // For UPDATE actions
  old_values?: Record<string, any>; // Previous values before update
  updated_fields?: string[]; // List of field names that were updated
  
  // For DELETE actions
  deleted_values?: Record<string, any>; // Values of the deleted entity
  
  // For STATUS_CHANGE actions
  previous_status?: string | boolean;
  new_status?: string | boolean;
  
  // Additional context
  affected_fields?: string[]; // Fields that were affected
  additional_info?: Record<string, any>; // Any other relevant information
  
  // Legacy support - keep existing fields
  [key: string]: any;
}

/**
 * Log an action to the audit log with enhanced details
 */
export const logAction = async (
  userId: string | null,
  actionType: ActionType,
  entityType: EntityType,
  entityId: string | null = null,
  details: AuditLogDetails = {}
): Promise<void> => {
  try {
    const clientInfo = getClientInfo();

    // Structure the details based on action type
    const structuredDetails: AuditLogDetails = {
      ...details,
      // Ensure proper structure for different action types
      ...(actionType === 'CREATE' && details.new_values ? { new_values: details.new_values } : {}),
      ...(actionType === 'UPDATE' && (details.old_values || details.new_values) ? {
        old_values: details.old_values || {},
        new_values: details.new_values || {},
        updated_fields: details.updated_fields || [],
      } : {}),
      ...(actionType === 'DELETE' && details.deleted_values ? { deleted_values: details.deleted_values } : {}),
      ...(actionType === 'STATUS_CHANGE' ? {
        previous_status: details.previous_status,
        new_status: details.new_status,
      } : {}),
    };

    const { error } = await supabase.from('audit_logs').insert({
      user_id: userId,
      action_type: actionType,
      entity_type: entityType,
      entity_id: entityId,
      details: structuredDetails,
      ip_address: clientInfo.ip_address,
      user_agent: clientInfo.user_agent,
    });

    if (error) {
      console.error('Error logging action:', error);
      // Don't throw error - audit logging should not break the main flow
    }
  } catch (error) {
    console.error('Failed to log action:', error);
    // Don't throw error - audit logging should not break the main flow
  }
};

/**
 * Fetch audit logs with optional filters
 */
export const fetchAuditLogs = async (filters: AuditLogFilters = {}): Promise<AuditLogWithUser[]> => {
  try {
    let query = supabase
      .from('audit_logs')
      .select(`
        *,
        app_users (
          name,
          email,
          role
        )
      `)
      .order('created_at', { ascending: false });

    if (filters.userId) {
      query = query.eq('user_id', filters.userId);
    }

    if (filters.actionType) {
      query = query.eq('action_type', filters.actionType);
    }

    if (filters.entityType) {
      query = query.eq('entity_type', filters.entityType);
    }

    if (filters.entityId) {
      query = query.eq('entity_id', filters.entityId);
    }

    if (filters.startDate) {
      query = query.gte('created_at', filters.startDate);
    }

    if (filters.endDate) {
      query = query.lte('created_at', filters.endDate);
    }

    if (filters.limit) {
      query = query.limit(filters.limit);
    }

    if (filters.offset) {
      query = query.range(filters.offset, filters.offset + (filters.limit || 100) - 1);
    }

    const { data, error } = await query;

    if (error) throw error;

    return (data || []).map((log: any) => ({
      ...log,
      app_users: Array.isArray(log.app_users) ? log.app_users[0] : log.app_users || null,
    })) as AuditLogWithUser[];
  } catch (error) {
    console.error('Error fetching audit logs:', error);
    throw error;
  }
};

/**
 * Fetch audit logs by user ID
 */
export const fetchAuditLogsByUser = async (userId: string, limit: number = 100): Promise<AuditLogWithUser[]> => {
  return fetchAuditLogs({ userId, limit });
};

/**
 * Fetch audit logs by entity
 */
export const fetchAuditLogsByEntity = async (
  entityType: EntityType,
  entityId: string,
  limit: number = 100
): Promise<AuditLogWithUser[]> => {
  return fetchAuditLogs({ entityType, entityId, limit });
};

/**
 * Get total count of audit logs matching filters
 */
export const getAuditLogsCount = async (filters: Omit<AuditLogFilters, 'limit' | 'offset'> = {}): Promise<number> => {
  try {
    let query = supabase.from('audit_logs').select('id', { count: 'exact', head: true });

    if (filters.userId) {
      query = query.eq('user_id', filters.userId);
    }

    if (filters.actionType) {
      query = query.eq('action_type', filters.actionType);
    }

    if (filters.entityType) {
      query = query.eq('entity_type', filters.entityType);
    }

    if (filters.entityId) {
      query = query.eq('entity_id', filters.entityId);
    }

    if (filters.startDate) {
      query = query.gte('created_at', filters.startDate);
    }

    if (filters.endDate) {
      query = query.lte('created_at', filters.endDate);
    }

    const { count, error } = await query;

    if (error) throw error;

    return count || 0;
  } catch (error) {
    console.error('Error getting audit logs count:', error);
    throw error;
  }
};
