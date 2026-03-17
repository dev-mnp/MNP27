// Type Definitions
// These interfaces are used throughout the application for type safety

export interface District {
  id: string;
  name: string;
  code?: string;
  allottedBudget: number;
  presidentName: string;
  mobileNumber: string;
}

export interface Article {
  id: string;
  name: string;
  costPerUnit: number;
  itemType: string; // Article, Aid, Project
  category?: string;
  sequenceList?: string;
  comments?: string;
}

export interface ArticleSelection {
  articleId: string;
  articleName: string;
  quantity: number;
  costPerUnit: number;
  totalValue: number;
  comments?: string; // Optional, kept for backward compatibility
  cheque_in_favour?: string; // For Article fund requests
  supplier_article_name?: string; // For Article fund requests
  description?: string; // For Article fund requests
}

export interface MasterEntryRecord {
  id: string;
  applicationNumber: string;
  beneficiaryType: 'district' | 'public' | 'institutions';
  createdAt: string;
  
  // District fields
  districtId?: string;
  districtName?: string;
  selectedArticles?: ArticleSelection[];
  totalAccrued?: number;
  
  // Public fields
  aadharNumber?: string;
  name?: string;
  handicapped?: boolean;
  gender?: 'Male' | 'Female' | 'Transgender';
  femaleStatus?: 'Single Mother' | 'Widow' | 'Married' | 'Unmarried';
  address?: string;
  mobile?: string;
  articleId?: string;
  quantity?: number;
  costPerUnit?: number;
  totalValue?: number;
  comments?: string;
  
  // Institutions fields
  institutionName?: string;
  institutionType?: 'institutions' | 'others';
}

// Institution types constant (used in forms)
export const institutionTypes = ['institutions', 'others'] as const;
