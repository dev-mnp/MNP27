import React, { createContext, useContext, useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { supabase, supabaseUrl } from '../lib/supabase';
import type { AuthUser } from '../lib/supabase';
import { fetchUserById } from '../services/userService';
import { logAction } from '../services/auditLogService';

interface AuthContextType {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isRestoringSession: boolean;
  login: (userData: AuthUser, session?: any) => Promise<void>;
  logout: () => Promise<void>;
  updateUser: (userData: Partial<AuthUser>) => void;
  hasPermission: (permission: string) => boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

interface AuthProviderProps {
  children: React.ReactNode;
}

type SessionValidationResult = {
  status: 'valid' | 'expired' | 'error';
  session: any | null;
  userProfile: AuthUser | null;
  error?: string;
};

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isRestoringSession, setIsRestoringSession] = useState(true);
  const healthCheckIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const isProcessingAuthChangeRef = useRef(false);
  const isRestoringSessionRef = useRef(false); // Prevent multiple simultaneous session restorations
  const justLoggedInRef = useRef(false); // Track if we just logged in to prevent focus handler interference

  // Fetch user profile from database
  const fetchUserProfile = useCallback(async (userId: string): Promise<AuthUser | null> => {
    try {
      const userProfile = await fetchUserById(userId);
      if (!userProfile || userProfile.status !== 'active') {
        return null;
      }

      return {
        id: userProfile.id,
        email: userProfile.email,
        name: userProfile.name || userProfile.email,
        first_name: userProfile.first_name || '',
        last_name: userProfile.last_name || '',
        role: userProfile.role,
        permissions: [],
        roles: [],
        created_at: userProfile.created_at,
      };
    } catch (error) {
      console.error('Error fetching user profile:', error);
      return null;
    }
  }, []);

  // Helper to get Supabase session from localStorage as fallback
  const getSessionFromStorage = useCallback((): any | null => {
    try {
      // Supabase stores session in localStorage with key: sb-{project-ref}-auth-token
      // Extract project ref from URL: https://miftepyeoqfjyjeqffet.supabase.co -> miftepyeoqfjyjeqffet
      const urlMatch = supabaseUrl.match(/https?:\/\/([^.]+)\.supabase\.co/);
      if (!urlMatch) {
        console.warn('Could not extract project ref from Supabase URL');
        return null;
      }
      const projectRef = urlMatch[1];
      const storageKey = `sb-${projectRef}-auth-token`;
      const stored = localStorage.getItem(storageKey);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (parsed && parsed.access_token && parsed.user) {
          console.debug('Found valid session in localStorage');
          return {
            access_token: parsed.access_token,
            refresh_token: parsed.refresh_token,
            expires_at: parsed.expires_at,
            expires_in: parsed.expires_in,
            token_type: parsed.token_type,
            user: parsed.user,
          };
        }
      }
    } catch (error) {
      console.warn('Error reading session from storage:', error);
    }
    return null;
  }, []);

  // Session validation and refresh utility
  const validateAndRefreshSession = useCallback(async (): Promise<SessionValidationResult> => {
    try {
      let session: any = null;
      let error: any = null;

      // Try to get session from Supabase (with longer timeout)
      try {
        const sessionPromise = supabase.auth.getSession();
        const timeoutPromise = new Promise<never>((_, reject) => {
          setTimeout(() => reject(new Error('Session check timeout')), 8000);
        });

        const result = await Promise.race([sessionPromise, timeoutPromise]);
        session = result.data?.session;
        error = result.error;
      } catch (timeoutError: any) {
        console.warn('getSession() timed out, trying localStorage fallback:', timeoutError.message);
        // Fallback to reading from localStorage directly
        const storedSession = getSessionFromStorage();
        if (storedSession) {
          // Set the session in Supabase client so API calls work
          try {
            const { data: setSessionData, error: setSessionError } = await supabase.auth.setSession({
              access_token: storedSession.access_token,
              refresh_token: storedSession.refresh_token,
            });
            if (setSessionError) {
              console.error('Error setting session from storage:', setSessionError);
              return {
                status: 'error',
                session: null,
                userProfile: null,
                error: 'Failed to set session from storage',
              };
            }
            session = setSessionData.session || storedSession;
            console.debug('Found session in localStorage and set it in Supabase client');
            // Continue to fetch user profile below - don't return yet
          } catch (setError) {
            console.error('Error setting session:', setError);
            return {
              status: 'error',
              session: null,
              userProfile: null,
              error: 'Failed to set session from storage',
            };
          }
        } else {
          return {
            status: 'error',
            session: null,
            userProfile: null,
            error: 'Session check timeout and no session in storage',
          };
        }
      }

      if (error && !session) {
        console.warn('Session check error, trying localStorage fallback:', error);
        // Fallback to reading from localStorage directly
        const storedSession = getSessionFromStorage();
        if (storedSession) {
          // Set the session in Supabase client so API calls work
          try {
            const { data: setSessionData, error: setSessionError } = await supabase.auth.setSession({
              access_token: storedSession.access_token,
              refresh_token: storedSession.refresh_token,
            });
            if (setSessionError) {
              console.error('Error setting session from storage:', setSessionError);
              return {
                status: 'error',
                session: null,
                userProfile: null,
                error: 'Failed to set session from storage',
              };
            }
            session = setSessionData.session || storedSession;
            console.debug('Found session in localStorage after error and set it in Supabase client');
            // Continue to fetch user profile below - don't return yet
          } catch (setError) {
            console.error('Error setting session:', setError);
            return {
              status: 'error',
              session: null,
              userProfile: null,
              error: 'Failed to set session from storage',
            };
          }
        } else {
          return {
            status: 'error',
            session: null,
            userProfile: null,
            error: error.message,
          };
        }
      }

      // No session found
      if (!session || !session.user) {
        return {
          status: 'expired',
          session: null,
          userProfile: null,
          error: 'No active session',
        };
      }

      // Check if session is expired
      const now = Math.floor(Date.now() / 1000);
      const expiresAt = session.expires_at || (session.expires_in ? now + session.expires_in : null);
      
      if (expiresAt && expiresAt < now) {
        // Try to refresh the session
        try {
          console.debug('Session expired, attempting refresh');
          const { data: refreshData, error: refreshError } = await supabase.auth.refreshSession();
          if (refreshError || !refreshData.session) {
            return {
              status: 'expired',
              session: null,
              userProfile: null,
              error: 'Session expired and refresh failed',
            };
          }
          // Use refreshed session
          const refreshedSession = refreshData.session;
          
          // Fetch user profile with timeout
          const profilePromise = fetchUserProfile(refreshedSession.user.id);
          const profileTimeout = new Promise<never>((_, reject) => {
            setTimeout(() => reject(new Error('Profile fetch timeout')), 5000);
          });
          
          const userProfile = await Promise.race([profilePromise, profileTimeout]);
          if (!userProfile) {
            return {
              status: 'expired',
              session: null,
              userProfile: null,
              error: 'User profile not found or inactive',
            };
          }
          return {
            status: 'valid',
            session: refreshedSession,
            userProfile,
          };
        } catch (refreshError: any) {
          console.error('Error refreshing session:', refreshError);
          return {
            status: 'expired',
            session: null,
            userProfile: null,
            error: refreshError.message || 'Failed to refresh session',
          };
        }
      }

      // Session is set, no need to verify again (avoids getSession() timeout)
      // The session was either from getSession() or we just set it from localStorage
      console.debug('Session available, proceeding to fetch user profile');

      // Session is valid, fetch user profile with timeout
      try {
        console.debug('Fetching user profile for user:', session.user.id);
        const profilePromise = fetchUserProfile(session.user.id);
        const profileTimeout = new Promise<never>((_, reject) => {
          setTimeout(() => reject(new Error('Profile fetch timeout')), 5000);
        });
        
        const userProfile = await Promise.race([profilePromise, profileTimeout]);
        if (!userProfile) {
          console.warn('User profile not found or inactive for user:', session.user.id);
          return {
            status: 'expired',
            session: null,
            userProfile: null,
            error: 'User profile not found or inactive',
          };
        }

        console.debug('User profile fetched successfully');
        return {
          status: 'valid',
          session,
          userProfile,
        };
      } catch (profileError: any) {
        console.error('Error fetching user profile:', profileError);
        // If profile fetch fails but we have a valid session, try to use saved user data
        const savedUser = localStorage.getItem('app-user');
        if (savedUser && session.user) {
          try {
            const userData = JSON.parse(savedUser);
            if (userData && userData.id === session.user.id) {
              console.debug('Using saved user data after profile fetch failure');
              return {
                status: 'valid',
                session,
                userProfile: userData,
              };
            }
          } catch (parseError) {
            console.error('Error parsing saved user data:', parseError);
          }
        }
        // If we can't get user profile, return error status
        return {
          status: 'error',
          session,
          userProfile: null,
          error: profileError.message || 'Failed to fetch user profile',
        };
      }
    } catch (error: any) {
      console.error('Error validating session:', error);
      return {
        status: 'error',
        session: null,
        userProfile: null,
        error: error.message || 'Unknown error during session validation',
      };
    }
  }, [fetchUserProfile, getSessionFromStorage]);

  // Helper to update auth state
  const updateAuthState = useCallback((userProfile: AuthUser | null, authenticated: boolean) => {
    setUser(userProfile);
    setIsAuthenticated(authenticated);
    if (userProfile && authenticated) {
      localStorage.setItem('app-user', JSON.stringify(userProfile));
      localStorage.setItem('app-authenticated', 'true');
    } else {
      localStorage.removeItem('app-user');
      localStorage.removeItem('app-authenticated');
    }
  }, []);


  // Check for existing session on mount
  useEffect(() => {
    let timeoutId: NodeJS.Timeout | null = null;

    const checkExistingSession = async () => {
      // Skip if already authenticated (e.g., from fresh login)
      if (isAuthenticated && user) {
        console.debug('Already authenticated, skipping restoration');
        setIsRestoringSession(false);
        return;
      }
      
      try {
        // PRIORITY 1: Check localStorage first (fastest, most reliable)
        // Since we know localStorage has the data, use it immediately
        const savedUser = localStorage.getItem('app-user');
        const savedAuth = localStorage.getItem('app-authenticated');
        
        if (savedUser && savedAuth === 'true') {
          try {
            const userData = JSON.parse(savedUser);
            
            // Validate user data structure
            if (userData && userData.id && userData.email) {
              console.debug('Found valid user data in localStorage, restoring immediately');
              
              // Set user state immediately for fast restoration
              setUser(userData);
              setIsAuthenticated(true);
              
              console.debug('User session restored from localStorage (fast path)');
              
              // Verify with Supabase session in background (non-blocking)
              // Don't wait for this - restoration is already complete
              supabase.auth.getSession().then(({ data: { session }, error }) => {
                if (session && !error && session.user.email === userData.email) {
                  console.debug('Supabase session verified, user is authenticated');
                } else if (error || !session) {
                  console.warn('Supabase session not found, but localStorage data is valid - keeping restored state');
                  // Keep the localStorage-based restoration even if Supabase session is missing
                  // This handles cases where Supabase session expired but user data is still valid
                }
              }).catch((sessionError) => {
                console.warn('Error verifying Supabase session (non-critical):', sessionError);
                // Don't clear localStorage on transient errors - keep the restored state
              });
              
              // Mark restoration as complete AFTER state is set
              setIsRestoringSession(false);
              return; // Successfully restored, exit early
            } else {
              // Invalid or malformed user data
              console.warn('Invalid user data structure in localStorage, will try Supabase session');
              // Don't clear yet - try Supabase session first
            }
          } catch (parseError) {
            console.error('Error parsing saved user data:', parseError);
            // Don't clear yet - try Supabase session first
          }
        }
        
        // PRIORITY 2: Check Supabase session if localStorage didn't work
        try {
          const { data: { session }, error } = await supabase.auth.getSession();
          
          if (session && !error) {
            console.debug('Active Supabase session found, restoring user state');
            
            try {
              // Get user profile from the session
              const userProfile = await fetchUserProfile(session.user.id);
              
              if (userProfile) {
                // Set user state immediately
                setUser(userProfile);
                setIsAuthenticated(true);
                
                // Update localStorage to match current session
                localStorage.setItem('app-user', JSON.stringify(userProfile));
                localStorage.setItem('app-authenticated', 'true');
                
                console.debug('User session restored from Supabase');
                // Mark restoration as complete AFTER state is set
                setIsRestoringSession(false);
                return;
              } else {
                console.warn('No user profile found for active session');
                // Don't clear localStorage - might be a transient error
              }
            } catch (profileError) {
              console.warn('Error getting user profile for active session:', profileError);
              // Don't clear localStorage on profile fetch errors - might be transient
            }
          } else {
            console.debug('No active Supabase session found');
          }
        } catch (sessionError) {
          console.warn('Error checking Supabase session (non-critical):', sessionError);
          // Don't clear localStorage on transient errors
        }
        
        // If we reach here, neither localStorage nor Supabase session worked
        // Only clear localStorage if we're certain there's no valid session
        console.debug('No valid session found, user needs to login');
        // Don't clear localStorage here - let the auth state listener handle it
        // This prevents clearing on transient network errors
        
      } catch (error) {
        console.error('Error checking existing session:', error);
        // Don't clear localStorage on errors - might be transient network issues
        // Only clear if we're certain the session is invalid
        console.warn('Session check failed, but keeping localStorage intact in case of transient error');
      } finally {
        setIsRestoringSession(false);
      }
    };

    checkExistingSession();

    // Cleanup function
    return () => {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [fetchUserProfile, isAuthenticated, user]);

  // Listen for Supabase auth state changes
  useEffect(() => {
    const { data: { subscription } } = supabase.auth.onAuthStateChange(async (event, session) => {
      // Prevent concurrent auth state changes
      if (isProcessingAuthChangeRef.current) {
        console.debug('Auth state change already processing, skipping:', event);
        return;
      }

      isProcessingAuthChangeRef.current = true;

      try {
        console.debug('Auth state change event:', event, session?.user?.email);

        if (event === 'SIGNED_IN' && session && session.user) {
          // Only process if we're not in the middle of a manual login or session restoration
          if (!isRestoringSession) {
            // If already authenticated, skip processing
            if (isAuthenticated) {
              console.debug('SIGNED_IN event ignored - user already authenticated');
              return;
            }
            
            console.debug('SIGNED_IN event - fetching user profile');
            justLoggedInRef.current = true; // Mark that we just logged in
            const userProfile = await fetchUserProfile(session.user.id);
            if (userProfile) {
              console.debug('SIGNED_IN: Updating auth state with user profile');
              updateAuthState(userProfile, true);
              
              // Reset the flag after a delay to allow components to load
              setTimeout(() => {
                justLoggedInRef.current = false;
              }, 5000); // 5 seconds should be enough for initial data loads
            } else {
              console.warn('SIGNED_IN: User profile not found');
              justLoggedInRef.current = false;
            }
          } else {
            console.debug('SIGNED_IN event ignored - manual login in progress');
          }
        } else if (event === 'SIGNED_OUT') {
          justLoggedInRef.current = false;
          updateAuthState(null, false);
        } else if (event === 'TOKEN_REFRESHED' && session && session.user) {
          // Token was refreshed, update user profile to ensure it's current
          console.debug('Token refreshed, updating user state');
          const userProfile = await fetchUserProfile(session.user.id);
          if (userProfile) {
            updateAuthState(userProfile, true);
          } else {
            // User profile no longer valid, sign out
            console.warn('User profile invalid after token refresh, signing out');
            try {
              await supabase.auth.signOut();
            } catch (error) {
              console.error('Error signing out after invalid profile:', error);
            }
            updateAuthState(null, false);
          }
        } else if (event === 'USER_UPDATED' && session && session.user) {
          // User data was updated, refresh profile
          console.debug('User updated, refreshing profile');
          const userProfile = await fetchUserProfile(session.user.id);
          if (userProfile) {
            updateAuthState(userProfile, true);
          }
        } else if (event === 'INITIAL_SESSION' && session && session.user) {
          // Initial session on mount - only process if we're not already restoring or authenticated
          if (!isRestoringSession && !isAuthenticated) {
            console.debug('Initial session detected, restoring user state');
            const userProfile = await fetchUserProfile(session.user.id);
            if (userProfile) {
              updateAuthState(userProfile, true);
            } else {
              updateAuthState(null, false);
            }
          } else {
            console.debug('INITIAL_SESSION ignored - already restoring or authenticated');
          }
        }
      } catch (error) {
        console.error('Error handling auth state change:', error);
        // On error, try to maintain current state if possible
        if (event === 'SIGNED_OUT') {
          updateAuthState(null, false);
        }
      } finally {
        isProcessingAuthChangeRef.current = false;
      }
    });

    return () => {
      subscription.unsubscribe();
    };
  }, [fetchUserProfile, updateAuthState, isRestoringSession, isAuthenticated]);

  // Handle visibility change (tab switching) to refresh session and check connection
  useEffect(() => {
    let isMounted = true;
    let refreshTimeoutId: NodeJS.Timeout | null = null;
    let isProcessing = false;

    const handleVisibilityChange = async () => {
      // Handle when tab becomes hidden
      if (document.visibilityState === 'hidden') {
        // Tab became hidden, reset processing flag
        isProcessing = false;
        if (refreshTimeoutId) {
          clearTimeout(refreshTimeoutId);
          refreshTimeoutId = null;
        }
        return;
      }
      
      // Only process when tab becomes visible
      if (document.visibilityState !== 'visible' || !isMounted || isProcessing) {
        return;
      }
      
      // Skip if we just logged in (within last 5 seconds)
      if (justLoggedInRef.current) {
        console.debug('Tab became visible, but skipping validation (just logged in)');
        return;
      }
      
      // If already authenticated, skip validation
      if (isAuthenticated) {
        console.debug('Tab became visible, but already authenticated, skipping');
        return;
      }
      
      isProcessing = true;
      try {
        // Clear any pending refresh
        if (refreshTimeoutId) {
          clearTimeout(refreshTimeoutId);
        }

        // Small delay to avoid rapid refreshes (debounce)
        refreshTimeoutId = setTimeout(async () => {
          if (!isMounted) {
            isProcessing = false;
            return;
          }
          
          // Double-check we didn't just log in
          if (justLoggedInRef.current) {
            console.debug('Tab visibility check skipped (just logged in)');
            isProcessing = false;
            return;
          }
          
          // If already authenticated, skip validation
          if (isAuthenticated) {
            console.debug('Tab visibility check skipped (already authenticated)');
            isProcessing = false;
            return;
          }

          // If not authenticated, try to restore from localStorage
          try {
            console.debug('Tab became visible, checking for saved session');
            const savedUser = localStorage.getItem('app-user');
            const savedAuth = localStorage.getItem('app-authenticated');
            
            if (savedUser && savedAuth === 'true' && isMounted) {
              try {
                const userData = JSON.parse(savedUser);
                if (userData && userData.id && userData.email) {
                  // Restore from localStorage (fast path)
                  setUser(userData);
                  setIsAuthenticated(true);
                  console.debug('Session restored from localStorage after tab visibility');
                }
              } catch (parseError) {
                console.error('Error parsing saved user data:', parseError);
              }
            }
          } catch (error) {
            console.warn('Error checking session on tab visibility:', error);
          } finally {
            isProcessing = false;
          }
        }, 500); // 500ms delay to debounce rapid visibility changes
      } catch (error) {
        console.error('Error in visibility change handler:', error);
        isProcessing = false;
      }
    };

    // Add event listener
    document.addEventListener('visibilitychange', handleVisibilityChange);

    // Cleanup
    return () => {
      isMounted = false;
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      if (refreshTimeoutId) {
        clearTimeout(refreshTimeoutId);
      }
    };
  }, [isAuthenticated]);

  // Handle window focus as additional recovery mechanism
  useEffect(() => {
    let isMounted = true;
    let focusTimeoutId: NodeJS.Timeout | null = null;
    let isProcessing = false;

    const handleFocus = async () => {
      if (!isMounted || isProcessing || document.visibilityState !== 'visible') {
        return;
      }

      // Skip focus handler if we just logged in (within last 5 seconds)
      if (justLoggedInRef.current) {
        console.debug('Window focused, but skipping validation (just logged in)');
        return;
      }
      
      // If already authenticated, skip validation
      if (isAuthenticated) {
        console.debug('Window focused, but already authenticated, skipping');
        return;
      }
      
      isProcessing = true;
      try {
        // Clear any pending focus check
        if (focusTimeoutId) {
          clearTimeout(focusTimeoutId);
        }

        // Small delay to avoid rapid checks (debounce)
        focusTimeoutId = setTimeout(async () => {
          if (!isMounted) {
            isProcessing = false;
            return;
          }
          
          // Double-check we didn't just log in
          if (justLoggedInRef.current) {
            console.debug('Window focus check skipped (just logged in)');
            isProcessing = false;
            return;
          }
          
          // If already authenticated, skip validation
          if (isAuthenticated) {
            console.debug('Window focus check skipped (already authenticated)');
            isProcessing = false;
            return;
          }

          // If not authenticated, try to restore from localStorage
          try {
            console.debug('Window focused, checking for saved session');
            const savedUser = localStorage.getItem('app-user');
            const savedAuth = localStorage.getItem('app-authenticated');
            
            if (savedUser && savedAuth === 'true' && isMounted) {
              try {
                const userData = JSON.parse(savedUser);
                if (userData && userData.id && userData.email) {
                  // Restore from localStorage (fast path)
                  setUser(userData);
                  setIsAuthenticated(true);
                  console.debug('Session restored from localStorage after window focus');
                }
              } catch (parseError) {
                console.error('Error parsing saved user data:', parseError);
              }
            }
          } catch (error) {
            console.warn('Error checking session on window focus:', error);
          } finally {
            isProcessing = false;
          }
        }, 300);
      } catch (error) {
        console.error('Error in focus handler:', error);
        isProcessing = false;
      }
    };

    window.addEventListener('focus', handleFocus);

    return () => {
      isMounted = false;
      window.removeEventListener('focus', handleFocus);
      if (focusTimeoutId) {
        clearTimeout(focusTimeoutId);
      }
    };
  }, [isAuthenticated]);

  // Periodic connection health check
  useEffect(() => {
    if (!isAuthenticated || !user) {
      // Clear any existing health check if user is not authenticated
      if (healthCheckIntervalRef.current) {
        clearInterval(healthCheckIntervalRef.current);
        healthCheckIntervalRef.current = null;
      }
      return;
    }

    // Start health check interval (every 5 minutes)
    healthCheckIntervalRef.current = setInterval(async () => {
      // Only check if tab is visible
      if (document.visibilityState === 'visible') {
        try {
          console.debug('Performing periodic session health check');
          const validation = await validateAndRefreshSession();

          if (validation.status === 'valid' && validation.userProfile) {
            // Session is valid, ensure state is up to date
            updateAuthState(validation.userProfile, true);
          } else if (validation.status === 'expired') {
            // Session expired, clear state
            console.warn('Session expired during health check');
            try {
              await supabase.auth.signOut();
            } catch (signOutError) {
              console.error('Error signing out:', signOutError);
            }
            updateAuthState(null, false);
          }
        } catch (error) {
          console.warn('Error during periodic health check:', error);
          // Don't clear session on transient errors
        }
      }
    }, 5 * 60 * 1000); // 5 minutes

    return () => {
      if (healthCheckIntervalRef.current) {
        clearInterval(healthCheckIntervalRef.current);
        healthCheckIntervalRef.current = null;
      }
    };
  }, [isAuthenticated, user, validateAndRefreshSession, updateAuthState]);

  const login = useCallback(async (userData: AuthUser, _session?: any) => {
    console.debug('Login: Starting login process for user:', userData.email);
    // Mark that we're logging in to prevent session restoration and focus handler from interfering
    isRestoringSessionRef.current = true;
    justLoggedInRef.current = true;
    
    // Set user state immediately - Supabase with persistSession: true handles the session automatically
    updateAuthState(userData, true);
    
    // Reset the flags after a delay to allow components to load data
    setTimeout(() => {
      isRestoringSessionRef.current = false;
      // Keep justLoggedInRef for a bit longer to prevent focus handler interference
      setTimeout(() => {
        justLoggedInRef.current = false;
      }, 3000); // 3 more seconds
    }, 2000); // 2 seconds total = 5 seconds before focus handler can run
  }, [updateAuthState]);

  const logout = async () => {
    try {
      // Clear health check interval
      if (healthCheckIntervalRef.current) {
        clearInterval(healthCheckIntervalRef.current);
        healthCheckIntervalRef.current = null;
      }

      // Log logout action before signing out
      if (user) {
        await logAction(user.id, 'LOGOUT', 'system', null, {
          email: user.email,
          role: user.role,
        });
      }

      await supabase.auth.signOut();
    } catch (error) {
      console.error('Error signing out from Supabase:', error);
    }
    
    updateAuthState(null, false);
  };

  const updateUser = (userData: Partial<AuthUser>) => {
    if (user) {
      const updatedUser = { ...user, ...userData };
      setUser(updatedUser);
      localStorage.setItem('app-user', JSON.stringify(updatedUser));
    }
  };

  const hasPermission = (permission: string): boolean => {
    if (!user) return false;
    // This will be enhanced by RBACContext
    return user.permissions?.includes(permission) || false;
  };

  // Memoize the context value to ensure components re-render when values change
  const value = useMemo(() => ({
    user,
    isAuthenticated,
    isRestoringSession,
    login,
    logout,
    updateUser,
    hasPermission,
  }), [user, isAuthenticated, isRestoringSession, login, logout, updateUser, hasPermission]);

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};
