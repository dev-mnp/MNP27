import { supabase } from '../lib/supabase';
import type { UserRole } from '../lib/supabase';
import { logAction } from './auditLogService';

export interface AppUser {
  id: string;
  email: string;
  name?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  role: UserRole;
  status: 'active' | 'inactive';
  created_at?: string;
  updated_at?: string;
}

export interface CreateUserData {
  email: string;
  password: string;
  first_name?: string;
  last_name?: string;
  role: UserRole;
}

export interface UpdateUserData {
  name?: string;
  first_name?: string;
  last_name?: string;
  role?: UserRole;
  status?: 'active' | 'inactive';
}

/**
 * Fetch all users
 */
export const fetchAllUsers = async (): Promise<AppUser[]> => {
  try {
    const { data, error } = await supabase
      .from('app_users')
      .select('*')
      .order('created_at', { ascending: false });

    if (error) throw error;
    return data || [];
  } catch (error) {
    console.error('Error fetching users:', error);
    throw error;
  }
};

/**
 * Fetch a single user by ID
 */
export const fetchUserById = async (userId: string): Promise<AppUser | null> => {
  try {
    const { data, error } = await supabase
      .from('app_users')
      .select('*')
      .eq('id', userId)
      .single();

    if (error) throw error;
    return data;
  } catch (error) {
    console.error('Error fetching user:', error);
    return null;
  }
};

/**
 * Fetch a single user by email
 */
export const fetchUserByEmail = async (email: string): Promise<AppUser | null> => {
  try {
    const { data, error } = await supabase
      .from('app_users')
      .select('*')
      .eq('email', email.toLowerCase())
      .single();

    if (error) throw error;
    return data;
  } catch (error) {
    console.error('Error fetching user by email:', error);
    return null;
  }
};

/**
 * Get current user ID from session
 */
const getCurrentUserId = async (): Promise<string | null> => {
  try {
    const { data: { session } } = await supabase.auth.getSession();
    return session?.user?.id || null;
  } catch {
    return null;
  }
};

/**
 * Create a new user (creates auth user and app_users record)
 * Uses signUp which doesn't require admin privileges
 * Note: User will need to confirm email unless email confirmation is disabled in Supabase
 */
export const createUser = async (userData: CreateUserData): Promise<AppUser> => {
  try {
    // Generate name from first_name and last_name
    const fullName = [userData.first_name, userData.last_name]
      .filter(Boolean)
      .join(' ')
      .trim() || userData.email;

    // Step 1: Create user in Supabase Auth using signUp
    const { data: authData, error: authError } = await supabase.auth.signUp({
      email: userData.email.toLowerCase(),
      password: userData.password,
      options: {
        data: {
          first_name: userData.first_name,
          last_name: userData.last_name,
          role: userData.role,
        },
      },
    });

    if (authError || !authData.user) {
      throw authError || new Error('Failed to create auth user');
    }

    // Step 2: Create app_users record
    const appUserData = {
      id: authData.user.id,
      email: userData.email.toLowerCase(),
      name: fullName,
      first_name: userData.first_name,
      last_name: userData.last_name,
      role: userData.role,
      status: 'active' as const,
    };

    const { data, error } = await supabase
      .from('app_users')
      .insert(appUserData)
      .select()
      .single();

    if (error) {
      // If app_users insert fails, we can't easily delete the auth user without admin
      // But the user won't be able to log in without the app_users record
      console.error('Failed to create app_users record:', error);
      throw new Error('User created but failed to set up profile. Please contact administrator.');
    }

    // Log audit action with new values
    const currentUserId = await getCurrentUserId();
    await logAction(currentUserId, 'CREATE', 'user', data.id, {
      entity_name: data.name || data.email,
      entity_summary: `User: ${data.email}`,
      new_values: {
        email: data.email,
        name: data.name,
        first_name: data.first_name,
        last_name: data.last_name,
        role: data.role,
        status: data.status,
      },
    });

    return data;
  } catch (error) {
    console.error('Error creating user:', error);
    throw error;
  }
};

/**
 * Update user
 */
export const updateUser = async (
  userId: string,
  userData: UpdateUserData
): Promise<AppUser> => {
  try {
    // Fetch old values before update
    const currentUser = await fetchUserById(userId);
    
    // Generate name from first_name and last_name if they're being updated
    let updateData = { ...userData };
    if (userData.first_name !== undefined || userData.last_name !== undefined) {
      const firstName = userData.first_name !== undefined ? userData.first_name : currentUser?.first_name || '';
      const lastName = userData.last_name !== undefined ? userData.last_name : currentUser?.last_name || '';
      const fullName = [firstName, lastName].filter(Boolean).join(' ').trim() || currentUser?.email || '';
      updateData.name = fullName;
    }

    const { data, error } = await supabase
      .from('app_users')
      .update(updateData)
      .eq('id', userId)
      .select()
      .single();

    if (error) throw error;

    // Log audit action with old and new values
    const currentUserId = await getCurrentUserId();
    const updatedFields = Object.keys(updateData);
    const oldValues: Record<string, any> = {};
    const newValues: Record<string, any> = {};

    updatedFields.forEach((field) => {
      if (currentUser) {
        oldValues[field] = currentUser[field as keyof typeof currentUser];
      }
      newValues[field] = updateData[field as keyof typeof updateData];
    });

    await logAction(currentUserId, 'UPDATE', 'user', userId, {
      entity_name: data.name || data.email,
      entity_summary: `User: ${data.email}`,
      old_values: oldValues,
      new_values: newValues,
      updated_fields: updatedFields,
      affected_fields: updatedFields,
    });

    return data;
  } catch (error) {
    console.error('Error updating user:', error);
    throw error;
  }
};

/**
 * Delete user (deletes from app_users only)
 * Note: Auth user deletion requires admin privileges, so we only delete from app_users
 * The auth user will remain but won't be able to log in without app_users record
 */
export const deleteUser = async (userId: string): Promise<void> => {
  try {
    // Get user details before deletion for audit log
    const userData = await fetchUserById(userId);

    // Delete from app_users
    // The user won't be able to log in without this record
    const { error: appError } = await supabase
      .from('app_users')
      .delete()
      .eq('id', userId);

    if (appError) throw appError;

    // Log audit action with deleted values
    const currentUserId = await getCurrentUserId();
    await logAction(currentUserId, 'DELETE', 'user', userId, {
      entity_name: userData?.name || userData?.email,
      entity_summary: `User: ${userData?.email}`,
      deleted_values: userData ? {
        email: userData.email,
        name: userData.name,
        first_name: userData.first_name,
        last_name: userData.last_name,
        role: userData.role,
        status: userData.status,
      } : {},
    });

    // Note: We can't delete from auth.users without admin privileges
    // For a complete deletion, use Supabase Dashboard or set up an admin endpoint
  } catch (error) {
    console.error('Error deleting user:', error);
    throw error;
  }
};

/**
 * Reset user password
 * Note: This requires admin privileges. For simple setup, users should reset their own passwords
 * via the forgot password flow in Supabase Auth
 */
export const resetUserPassword = async (_userId: string, _newPassword: string): Promise<void> => {
  try {
    // This requires admin privileges which we don't have in client-side code
    // For a simple system, users should use the password reset flow
    throw new Error('Password reset requires admin privileges. Please use the forgot password feature.');
  } catch (error) {
    console.error('Error resetting password:', error);
    throw error;
  }
};
