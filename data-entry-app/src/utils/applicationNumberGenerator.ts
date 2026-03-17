import { supabase } from '../lib/supabase';

/**
 * Generate application number based on beneficiary type from database
 * Format: [Type Prefix] [Sequential Number]
 * Prefixes: D (District), P (Public), I (Institutions)
 * For district type, queries the database for existing application numbers
 */
export const generateApplicationNumberFromDB = async (
  beneficiaryType: 'district' | 'public' | 'institutions'
): Promise<string> => {
  const prefix = beneficiaryType === 'district' ? 'D' : beneficiaryType === 'public' ? 'P' : 'I';

  // For district type, query database
  if (beneficiaryType === 'district') {
    try {
      const { data, error } = await supabase
        .from('district_beneficiary_entries')
        .select('application_number')
        .not('application_number', 'is', null);

      if (error) {
        console.error('Error fetching application numbers from database:', error);
        // Fallback to mock data method
        return generateApplicationNumber(beneficiaryType);
      }

      // Extract numbers from application numbers
      // Handle both old format (with space: "D 001") and new format (without space: "D001")
      const numbers = (data || [])
        .map((entry) => {
          const appNumber = entry.application_number;
          if (!appNumber || typeof appNumber !== 'string') return 0;
          
          // Check if it starts with "D" (district prefix) - handle both "D " and "D" formats
          if (!appNumber.startsWith('D')) return 0;
          
          // Extract the number part (handles both "D 001" and "D001" formats)
          const match = appNumber.match(/D\s*(\d+)$/);
          return match ? parseInt(match[1], 10) : 0;
        })
        .filter((n) => n > 0);

      // Get the highest number or default to 0
      const highestNumber = numbers.length > 0 ? Math.max(...numbers) : 0;

      // Generate next number (starts with 001, so if highest is 0, next is 1)
      const nextNumber = highestNumber + 1;

      // Format with leading zeros (3 digits) - ensures 001, 002, etc.
      const formattedNumber = nextNumber.toString().padStart(3, '0');

      return `${prefix}${formattedNumber}`;
    } catch (error) {
      console.error('Failed to generate application number from database:', error);
      // Fallback to mock data method
      return generateApplicationNumber(beneficiaryType);
    }
  }

  // For public type, query database
  if (beneficiaryType === 'public') {
    try {
      const { data, error } = await supabase
        .from('public_beneficiary_entries')
        .select('application_number')
        .not('application_number', 'is', null);

      if (error) {
        console.error('Error fetching application numbers from database:', error);
        // Fallback to timestamp-based generation
        return generateApplicationNumber(beneficiaryType);
      }

      // Extract numbers from application numbers
      // Handle both old format (with space: "P 001") and new format (without space: "P001")
      const numbers = (data || [])
        .map((entry) => {
          const appNumber = entry.application_number;
          if (!appNumber || typeof appNumber !== 'string') return 0;
          
          // Check if it starts with "P" (public prefix) - handle both "P " and "P" formats
          if (!appNumber.startsWith('P')) return 0;
          
          // Extract the number part (handles both "P 001" and "P001" formats)
          const match = appNumber.match(/P\s*(\d+)$/);
          return match ? parseInt(match[1], 10) : 0;
        })
        .filter((n) => n > 0);

      // Get the highest number or default to 0
      const highestNumber = numbers.length > 0 ? Math.max(...numbers) : 0;

      // Generate next number (starts with 001, so if highest is 0, next is 1)
      const nextNumber = highestNumber + 1;

      // Format with leading zeros (3 digits) - ensures 001, 002, etc.
      const formattedNumber = nextNumber.toString().padStart(3, '0');

      return `${prefix}${formattedNumber}`;
    } catch (error) {
      console.error('Failed to generate application number from database:', error);
      // Fallback to timestamp-based generation
      return generateApplicationNumber(beneficiaryType);
    }
  }

  // For institutions type, query database
  if (beneficiaryType === 'institutions') {
    try {
      const { data, error } = await supabase
        .from('institutions_beneficiary_entries')
        .select('application_number')
        .not('application_number', 'is', null);

      if (error) {
        console.error('Error fetching application numbers from database:', error);
        // Fallback to timestamp-based generation
        return generateApplicationNumber(beneficiaryType);
      }

      // Extract numbers from application numbers
      // Handle both old format (with space: "I 001") and new format (without space: "I001")
      const numbers = (data || [])
        .map((entry) => {
          const appNumber = entry.application_number;
          if (!appNumber || typeof appNumber !== 'string') return 0;
          
          // Check if it starts with "I" (institutions prefix) - handle both "I " and "I" formats
          if (!appNumber.startsWith('I')) return 0;
          
          // Extract the number part (handles both "I 001" and "I001" formats)
          const match = appNumber.match(/I\s*(\d+)$/);
          return match ? parseInt(match[1], 10) : 0;
        })
        .filter((n) => n > 0);

      // Get the highest number or default to 0
      const highestNumber = numbers.length > 0 ? Math.max(...numbers) : 0;

      // Generate next number (starts with 001, so if highest is 0, next is 1)
      const nextNumber = highestNumber + 1;

      // Format with leading zeros (3 digits) - ensures 001, 002, etc.
      const formattedNumber = nextNumber.toString().padStart(3, '0');

      return `${prefix}${formattedNumber}`;
    } catch (error) {
      console.error('Failed to generate application number from database:', error);
      // Fallback to timestamp-based generation
      return generateApplicationNumber(beneficiaryType);
    }
  }

  // Fallback (should not reach here)
  return generateApplicationNumber(beneficiaryType);
};

/**
 * Generate application number based on beneficiary type
 * Format: [Type Prefix] [Sequential Number]
 * Prefixes: D (District), P (Public), I (Institutions)
 * Uses timestamp-based generation as fallback when DB is not available
 */
export const generateApplicationNumber = (beneficiaryType: 'district' | 'public' | 'institutions'): string => {
  const prefix = beneficiaryType === 'district' ? 'D' : beneficiaryType === 'public' ? 'P' : 'I';
  
  // For fallback, use timestamp-based generation
  // This ensures unique numbers even without DB access
  // Start with 001 (not 000) - use modulo 999 + 1 to get range 1-999
  const timestamp = Date.now();
  const number = ((timestamp % 999) + 1).toString().padStart(3, '0');
  
  return `${prefix}${number}`;
};

/**
 * Validate application number format
 * Accepts both old format (with space: "D 001") and new format (without space: "D001")
 */
export const isValidApplicationNumber = (appNumber: string): boolean => {
  // Accept both formats: "D001" or "D 001"
  const pattern = /^[DPI]\s?\d{3}$/;
  return pattern.test(appNumber);
};

/**
 * Extract beneficiary type from application number
 * Handles both old format (with space: "D 001") and new format (without space: "D001")
 */
export const getBeneficiaryTypeFromAppNumber = (appNumber: string): 'district' | 'public' | 'institutions' | null => {
  if (appNumber.startsWith('D')) return 'district';
  if (appNumber.startsWith('P')) return 'public';
  if (appNumber.startsWith('I')) return 'institutions';
  return null;
};
