import { createClient } from '@supabase/supabase-js';

export const supabaseUrl = 'https://miftepyeoqfjyjeqffet.supabase.co';// import.meta.env.VITE_SUPABASE_URL;
export const supabaseAnonKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1pZnRlcHllb3FmanlqZXFmZmV0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjU3ODY5NzgsImV4cCI6MjA4MTM2Mjk3OH0.19nAsbnhQmTNrp6XqZ-iiUULMW8tnwSHIx5GbP5-cGY';// import.meta.env.VITE_SUPABASE_ANON_KEY;
// export const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
// export const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
console.log(supabaseUrl, supabaseAnonKey);
if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error('Missing Supabase environment variables. Please check your .env file.');
}

// Create Supabase client with proper configuration
export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
});


/**
 * Helper function to wrap Supabase queries with timeout and retry logic
 * @param queryFn - The Supabase query function to execute
 * @param maxRetries - Maximum number of retries (default: 1)
 * @param timeoutMs - Timeout in milliseconds (default: 10000)
 */
export async function withTimeoutAndRetry<T>(
  queryFn: () => Promise<T>,
  maxRetries: number = 1,
  timeoutMs: number = 10000
): Promise<T> {
  // Supabase client with persistSession: true automatically uses session from localStorage
  // No need to verify session - just proceed with the API call
  
  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const timeoutPromise = new Promise<never>((_, reject) => {
        setTimeout(() => reject(new Error(`Query timeout after ${timeoutMs}ms`)), timeoutMs);
      });

      const result = await Promise.race([queryFn(), timeoutPromise]);
      return result;
    } catch (error) {
      lastError = error as Error;
      
      // Don't retry on timeout or abort errors
      if (error instanceof Error && 
          (error.message.includes('timeout') || error.message.includes('aborted'))) {
        throw error;
      }

      // If this was the last attempt, throw the error
      if (attempt === maxRetries) {
        throw error;
      }

      // Wait before retrying (exponential backoff)
      await new Promise(resolve => setTimeout(resolve, Math.min(1000 * Math.pow(2, attempt), 5000)));
    }
  }

  throw lastError || new Error('Query failed after retries');
}

// User role types
export type UserRole = 'admin' | 'editor' | 'viewer';

// Auth user interface
export interface AuthUser {
  id: string;
  email: string;
  name?: string;
  first_name?: string;
  last_name?: string;
  role: UserRole;
  permissions?: string[];
  roles?: string[];
  created_at?: string;
}
