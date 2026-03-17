/**
 * Auto-Save Utility for Fund Request Forms
 * Handles saving and restoring form drafts to/from localStorage
 */

import type { FundRequest } from '../services/fundRequestService';
import type { ArticleSelection } from '../data/mockData';

export interface RecipientFormData {
  beneficiaryType?: 'District' | 'Public' | 'Institutions' | 'Others';
  recipient_name?: string;
  beneficiary?: string;
  name_of_beneficiary?: string;
  name_of_institution?: string;
  details?: string;
  fund_requested?: number;
  aadhar_number?: string;
  address?: string;
  cheque_in_favour?: string;
  cheque_no?: string;
  notes?: string;
  district_name?: string;
  beneficiaryOptions?: any[];
  loadingBeneficiaries?: boolean;
  selectedDistrictId?: string;
}

export interface ArticleDetails {
  beneficiary?: string;
  gst_no?: string;
  price_including_gst?: number;
  supplier_article_name?: string;
  cheque_in_favour?: string;
  cheque_no?: string;
}

export interface FundRequestDraft {
  fundRequestType: 'Aid' | 'Article';
  formData: Partial<FundRequest>;
  recipients: RecipientFormData[];
  selectedArticles: ArticleSelection[];
  gstNumber: string;
  supplierName: string;
  supplierAddress: string;
  supplierCity: string;
  supplierState: string;
  supplierPincode: string;
  articleDetails: Array<[string, ArticleDetails]>; // Convert Map to array for JSON
  selectedBeneficiaries: string[]; // Convert Set to array
  timestamp: number;
}

const STORAGE_KEY_PREFIX = 'fund-request-draft';

/**
 * Get storage key for draft
 */
const getStorageKey = (id?: string): string => {
  return id ? `${STORAGE_KEY_PREFIX}-${id}` : `${STORAGE_KEY_PREFIX}-new`;
};

/**
 * Save fund request draft to localStorage
 */
export const saveFundRequestDraft = (
  data: Omit<FundRequestDraft, 'timestamp'>,
  id?: string
): void => {
  try {
    const draft: FundRequestDraft = {
      ...data,
      timestamp: Date.now(),
    };

    const storageKey = getStorageKey(id);
    localStorage.setItem(storageKey, JSON.stringify(draft));
  } catch (error) {
    // Handle quota exceeded or other localStorage errors
    if (error instanceof Error && error.name === 'QuotaExceededError') {
      console.warn('LocalStorage quota exceeded. Cannot save draft.');
    } else {
      console.error('Error saving draft to localStorage:', error);
    }
  }
};

/**
 * Load fund request draft from localStorage
 */
export const loadFundRequestDraft = (id?: string): FundRequestDraft | null => {
  try {
    const storageKey = getStorageKey(id);
    const saved = localStorage.getItem(storageKey);
    
    if (!saved) {
      return null;
    }

    const draft: FundRequestDraft = JSON.parse(saved);
    
    // Validate draft structure
    if (!draft || typeof draft.timestamp !== 'number') {
      return null;
    }

    // Check if draft is too old (older than 7 days)
    const maxAge = 7 * 24 * 60 * 60 * 1000; // 7 days in milliseconds
    if (Date.now() - draft.timestamp > maxAge) {
      // Auto-cleanup old drafts
      clearFundRequestDraft(id);
      return null;
    }

    return draft;
  } catch (error) {
    console.error('Error loading draft from localStorage:', error);
    return null;
  }
};

/**
 * Clear fund request draft from localStorage
 */
export const clearFundRequestDraft = (id?: string): void => {
  try {
    const storageKey = getStorageKey(id);
    localStorage.removeItem(storageKey);
  } catch (error) {
    console.error('Error clearing draft from localStorage:', error);
  }
};

/**
 * Get draft timestamp
 */
export const getDraftTimestamp = (id?: string): number | null => {
  const draft = loadFundRequestDraft(id);
  return draft?.timestamp || null;
};

/**
 * Check if draft exists
 */
export const hasDraft = (id?: string): boolean => {
  return loadFundRequestDraft(id) !== null;
};

/**
 * Format timestamp for display
 */
export const formatDraftTimestamp = (timestamp: number): string => {
  const date = new Date(timestamp);
  return date.toLocaleString();
};

