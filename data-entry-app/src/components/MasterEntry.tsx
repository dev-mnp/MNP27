import React, { useState, useEffect, useRef } from 'react';
import { Plus, X, Save, Trash2, Pencil, Download, Loader2, Info, RefreshCw, ChevronDown, ChevronRight, Search } from 'lucide-react';
import {
  institutionTypes,
} from '../data/mockData';
import { exportToCSV } from '../utils/csvExport';
import { logAction } from '../services/auditLogService';
import { useAuth } from '../contexts/AuthContext';
import { supabase } from '../lib/supabase';
import { useNotifications } from '../contexts/NotificationContext';
import { ConfirmDialog } from './ConfirmDialog';
import type {
  MasterEntryRecord,
  Article,
  District,
  ArticleSelection,
} from '../data/mockData';
import { generateApplicationNumberFromDB } from '../utils/applicationNumberGenerator';
import MultiSelectArticles from './MultiSelectArticles';
import { useRBAC } from '../contexts/RBACContext';
import { fetchArticles, fetchAllArticles } from '../services/articlesService';
import type { ArticleRecord } from '../services/articlesService';
import { fetchDistricts, updateDistrictApplicationNumber, getDistrictApplicationNumber } from '../services/districtsService';
import {
  createDistrictBeneficiaryEntries,
  fetchDistrictBeneficiaryEntriesGrouped,
  deleteDistrictBeneficiaryEntriesByApplicationNumber,
  fetchDistrictBeneficiaryEntries,
  fetchDistrictBeneficiaryEntryByDistrictId,
} from '../services/districtBeneficiaryService';
import {
  createInstitutionBeneficiaryEntries,
  fetchInstitutionBeneficiaryEntriesGrouped,
  deleteInstitutionBeneficiaryEntriesByApplicationNumber,
} from '../services/institutionBeneficiaryService';
import { CURRENCY_SYMBOL } from '../constants/currency';

type BeneficiaryType = 'district' | 'public' | 'institutions';

const MasterEntry: React.FC = () => {
  const { user, isAuthenticated, isRestoringSession } = useAuth();
  const { canDelete, canCreate, canUpdate, canExport } = useRBAC();
  const { showError, showSuccess, showWarning } = useNotifications();
  const [beneficiaryTypeFilter, setBeneficiaryTypeFilter] = useState<BeneficiaryType>('district');
  const [isFormMode, setIsFormMode] = useState(false);
  const [editingRecordId, setEditingRecordId] = useState<string | null>(null);
  const [records, setRecords] = useState<MasterEntryRecord[]>([]);
  const [articles, setArticles] = useState<Article[]>([]);
  const [loadingArticles, setLoadingArticles] = useState(true);
  const [districts, setDistricts] = useState<District[]>([]);
  const [loadingDistricts, setLoadingDistricts] = useState(true);
  const [loadingRecords, setLoadingRecords] = useState(true);
  const [existingDistrictEntriesTotal, setExistingDistrictEntriesTotal] = useState(0);
  const [loadingExistingEntries, setLoadingExistingEntries] = useState(true);
  const [showExportModal, setShowExportModal] = useState(false);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [exportType, setExportType] = useState<'all' | 'district' | 'public' | 'institutions'>('all');
  const [exporting, setExporting] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [dateFilter, setDateFilter] = useState<{ start: string | null, end: string | null }>({ start: null, end: null });
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [confirmDialog, setConfirmDialog] = useState<{
    isOpen: boolean;
    title: string;
    message: string | React.ReactNode;
    onConfirm: () => void;
    onSecondary?: () => void;
    type?: 'danger' | 'warning' | 'info';
    confirmText?: string;
    secondaryText?: string;
  }>({
    isOpen: false,
    title: '',
    message: '',
    onConfirm: () => { },
  });

  // Form state
  const [formData, setFormData] = useState<Partial<MasterEntryRecord>>({
    beneficiaryType: 'district',
  });

  // Validation errors
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Aadhar verification state
  const [isVerifyingAadhar, setIsVerifyingAadhar] = useState(false);
  const [isAadharVerified, setIsAadharVerified] = useState(false);
  const [matchedHistoryRecords, setMatchedHistoryRecords] = useState<any[]>([]);

  // Save loading state
  const [isSaving, setSaving] = useState(false);
  
  // Delete loading state
  const [isDeleting, setIsDeleting] = useState(false);
  
  // Track loading state to prevent duplicate calls
  const isLoadingArticlesRef = useRef(false);
  const isLoadingDistrictsRef = useRef(false);

  // Fetch articles from database on component mount - only when authenticated and not restoring
  useEffect(() => {
    if (!isAuthenticated || isRestoringSession) {
      return;
    }
    
    // Prevent duplicate calls
    if (isLoadingArticlesRef.current) {
      return;
    }
    
    isLoadingArticlesRef.current = true;
    const loadStartTime = Date.now();
    console.debug('MasterEntry: Starting to load articles');
    
    const loadArticles = async () => {
      try {
        setLoadingArticles(true);
        const fetchedArticles = await fetchArticles();
        const loadDuration = Date.now() - loadStartTime;
        console.debug(`MasterEntry: Articles loaded in ${loadDuration}ms, count: ${fetchedArticles?.length || 0}`);
        setArticles(fetchedArticles);
      } catch (error) {
        const loadDuration = Date.now() - loadStartTime;
        console.error(`MasterEntry: Failed to load articles after ${loadDuration}ms:`, error);
        setArticles([]);
      } finally {
        isLoadingArticlesRef.current = false;
        setLoadingArticles(false);
      }
    };

    loadArticles();
    
    return () => {
      // Reset loading flag on unmount so remount can fetch again
      isLoadingArticlesRef.current = false;
    };
  }, [isAuthenticated, isRestoringSession]);

  // Fetch districts from database on component mount - only when authenticated and not restoring
  useEffect(() => {
    if (!isAuthenticated || isRestoringSession) {
      return;
    }
    
    // Prevent duplicate calls
    if (isLoadingDistrictsRef.current) {
      return;
    }
    
    isLoadingDistrictsRef.current = true;
    const loadStartTime = Date.now();
    console.debug('MasterEntry: Starting to load districts');
    
    const loadDistricts = async () => {
      try {
        setLoadingDistricts(true);
        const fetchedDistricts = await fetchDistricts();
        const loadDuration = Date.now() - loadStartTime;
        console.debug(`MasterEntry: Districts loaded in ${loadDuration}ms, count: ${fetchedDistricts?.length || 0}`);
        setDistricts(fetchedDistricts);
      } catch (error) {
        const loadDuration = Date.now() - loadStartTime;
        console.error(`MasterEntry: Failed to load districts after ${loadDuration}ms:`, error);
        setDistricts([]);
      } finally {
        isLoadingDistrictsRef.current = false;
        setLoadingDistricts(false);
      }
    };

    loadDistricts();
    
    return () => {
      // Reset loading flag on unmount so remount can fetch again
      isLoadingDistrictsRef.current = false;
    };
  }, [isAuthenticated, isRestoringSession]);

  // Load records when filter changes - only when authenticated and not restoring
  const isLoadingRecordsRef = useRef(false);
  
  // Load records function - extracted for reuse
  const loadRecords = async () => {
    if (!isAuthenticated || isRestoringSession) {
      return;
    }
    
    // Prevent duplicate calls
    if (isLoadingRecordsRef.current) {
      return;
    }
    
    isLoadingRecordsRef.current = true;
    const loadStartTime = Date.now();
    console.debug(`MasterEntry: Starting to load records for filter: ${beneficiaryTypeFilter}`);
    
    try {
      setLoadingRecords(true);

      if (beneficiaryTypeFilter === 'district') {
        // Fetch from database for district type
        const dbRecords = await fetchDistrictBeneficiaryEntriesGrouped();
        const loadDuration = Date.now() - loadStartTime;
        console.debug(`MasterEntry: District records loaded in ${loadDuration}ms, count: ${dbRecords?.length || 0}`);
        setRecords(dbRecords);
      } else if (beneficiaryTypeFilter === 'public') {
        // Fetch from database for public type
        const { data, error } = await supabase
          .from('public_beneficiary_entries')
          .select(`
            id,
            application_number,
            name,
            aadhar_number,
            is_handicapped,
            gender,
            female_status,
            address,
            mobile,
            article_id,
            quantity,
            total_amount,
            notes,
            status,
            created_at
          `)
          .order('created_at', { ascending: false });

        if (error) throw error;

        // Transform to MasterEntryRecord format
        const publicRecords: MasterEntryRecord[] = (data || []).map((entry: any) => ({
          id: entry.id,
          applicationNumber: entry.application_number || '',
          beneficiaryType: 'public' as const,
          createdAt: entry.created_at,
          aadharNumber: entry.aadhar_number,
          name: entry.name,
          handicapped: entry.is_handicapped,
          gender: entry.gender as 'Male' | 'Female' | 'Transgender' | undefined,
          femaleStatus: entry.female_status as 'Single Mother' | 'Widow' | 'Married' | 'Unmarried' | undefined,
          address: entry.address,
          mobile: entry.mobile,
          articleId: entry.article_id,
          quantity: entry.quantity,
          costPerUnit: entry.quantity > 0 ? (entry.total_amount / entry.quantity) : 0,
          totalValue: entry.total_amount,
          comments: entry.notes || '',
        }));

        const loadDuration = Date.now() - loadStartTime;
        console.debug(`MasterEntry: Public records loaded in ${loadDuration}ms, count: ${publicRecords?.length || 0}`);
        setRecords(publicRecords);
      } else if (beneficiaryTypeFilter === 'institutions') {
        // Fetch from database for institutions type
        const dbRecords = await fetchInstitutionBeneficiaryEntriesGrouped();
        const loadDuration = Date.now() - loadStartTime;
        console.debug(`MasterEntry: Institutions records loaded in ${loadDuration}ms, count: ${dbRecords?.length || 0}`);
        setRecords(dbRecords);
      }
    } catch (error) {
      const loadDuration = Date.now() - loadStartTime;
      console.error(`MasterEntry: Failed to load records after ${loadDuration}ms:`, error);
      setRecords([]);
      if (beneficiaryTypeFilter === 'public') {
        showError('Failed to load public beneficiary entries. Please try again.');
      } else if (beneficiaryTypeFilter === 'institutions') {
        showError('Failed to load institution beneficiary entries. Please try again.');
      } else {
        showError('Failed to load records. Please try again.');
      }
    } finally {
      isLoadingRecordsRef.current = false;
      setLoadingRecords(false);
      const loadDuration = Date.now() - loadStartTime;
      console.debug(`MasterEntry: loadRecords completed in ${loadDuration}ms`);
    }
  };

  useEffect(() => {
    loadRecords();
    
    return () => {
      // Reset loading flag on unmount so remount can fetch again
      isLoadingRecordsRef.current = false;
    };
  }, [beneficiaryTypeFilter, isAuthenticated, isRestoringSession]);

  // Handle column sorting
  const handleSort = (column: string) => {
    if (sortColumn === column) {
      // Toggle direction if same column
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      // New column, default to ascending
      setSortColumn(column);
      setSortDirection('asc');
    }
  };

  // Filter and sort records
  const getFilteredAndSortedRecords = (): MasterEntryRecord[] => {
    let filtered = [...records];

    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter((record) => {
        if (beneficiaryTypeFilter === 'district') {
          const districtArticleText = (record.selectedArticles || [])
            .map(article => article.articleName || '')
            .join(' ')
            .toLowerCase();
          return (
            record.applicationNumber?.toLowerCase().includes(query) ||
            record.districtName?.toLowerCase().includes(query) ||
            districtArticleText.includes(query)
          );
        } else if (beneficiaryTypeFilter === 'public') {
          const publicArticleName = getArticleById(record.articleId || '')?.name?.toLowerCase() || '';
          return (
            record.applicationNumber?.toLowerCase().includes(query) ||
            record.name?.toLowerCase().includes(query) ||
            record.aadharNumber?.toLowerCase().includes(query) ||
            record.mobile?.toLowerCase().includes(query) ||
            publicArticleName.includes(query)
          );
        } else if (beneficiaryTypeFilter === 'institutions') {
          const institutionArticleText = (record.selectedArticles || [])
            .map(article => article.articleName || '')
            .join(' ')
            .toLowerCase();
          return (
            record.applicationNumber?.toLowerCase().includes(query) ||
            record.institutionName?.toLowerCase().includes(query) ||
            institutionArticleText.includes(query)
          );
        }
        return false;
      });
    }

    // Apply date filter
    if (dateFilter.start || dateFilter.end) {
      filtered = filtered.filter((record) => {
        if (!record.createdAt) return false;
        
        const recordDate = new Date(record.createdAt);
        recordDate.setHours(0, 0, 0, 0);
        
        if (dateFilter.start) {
          const startDate = new Date(dateFilter.start);
          startDate.setHours(0, 0, 0, 0);
          if (recordDate < startDate) return false;
        }
        
        if (dateFilter.end) {
          const endDate = new Date(dateFilter.end);
          endDate.setHours(23, 59, 59, 999);
          if (recordDate > endDate) return false;
        }
        
        return true;
      });
    }

    // Apply sorting
    if (sortColumn) {
      filtered.sort((a, b) => {
        let aValue: any;
        let bValue: any;

        switch (sortColumn) {
          case 'applicationNumber':
            aValue = a.applicationNumber || '';
            bValue = b.applicationNumber || '';
            break;
          case 'districtName':
            aValue = a.districtName || '';
            bValue = b.districtName || '';
            break;
          case 'name':
            aValue = a.name || '';
            bValue = b.name || '';
            break;
          case 'aadharNumber':
            aValue = a.aadharNumber || '';
            bValue = b.aadharNumber || '';
            break;
          case 'gender':
            aValue = a.gender || '';
            bValue = b.gender || '';
            break;
          case 'article':
            aValue = getArticleById(a.articleId || '')?.name || '';
            bValue = getArticleById(b.articleId || '')?.name || '';
            break;
          case 'totalValue':
            aValue = a.totalValue || 0;
            bValue = b.totalValue || 0;
            break;
          case 'totalAccrued':
            aValue = a.totalAccrued || 0;
            bValue = b.totalAccrued || 0;
            break;
          case 'remainingFund':
            // Calculate remaining fund for district
            if (a.districtId) {
              const district = getDistrictById(a.districtId);
              aValue = district ? district.allottedBudget - (a.totalAccrued || 0) : 0;
            } else {
              aValue = 0;
            }
            if (b.districtId) {
              const district = getDistrictById(b.districtId);
              bValue = district ? district.allottedBudget - (b.totalAccrued || 0) : 0;
            } else {
              bValue = 0;
            }
            break;
          case 'handicapped':
            aValue = a.handicapped ? 1 : 0;
            bValue = b.handicapped ? 1 : 0;
            break;
          case 'institutionType':
            aValue = a.institutionType || '';
            bValue = b.institutionType || '';
            break;
          case 'articlesCount':
            aValue = a.selectedArticles?.length || 0;
            bValue = b.selectedArticles?.length || 0;
            break;
          case 'createdAt':
            aValue = a.createdAt ? new Date(a.createdAt).getTime() : 0;
            bValue = b.createdAt ? new Date(b.createdAt).getTime() : 0;
            break;
          default:
            return 0;
        }

        // Compare values
        if (typeof aValue === 'string' && typeof bValue === 'string') {
          return sortDirection === 'asc'
            ? aValue.localeCompare(bValue)
            : bValue.localeCompare(aValue);
        } else {
          return sortDirection === 'asc' ? aValue - bValue : bValue - aValue;
        }
      });
    }

    return filtered;
  };

  // Get sort icon for column header - always show indicators
  const getSortIcon = (column: string) => {
    if (sortColumn === column) {
      // Show active sort direction
      return sortDirection === 'asc' ? '↑' : '↓';
    }
    // Show both arrows (lighter color) to indicate sortable
    return '⇅';
  };


  // Helper function to get article by ID
  const getArticleById = (id: string): Article | undefined => {
    return articles.find(a => a.id === id);
  };

  // Helper function to get district by ID
  const getDistrictById = (id: string): District | undefined => {
    return districts.find(d => d.id === id);
  };

  // Helper function to detect duplicate articles
  const getDuplicateArticles = (selectedArticles: ArticleSelection[]): Array<{ name: string, count: number }> => {
    const articleCounts = new Map<string, number>();

    selectedArticles.forEach(article => {
      const count = articleCounts.get(article.articleId) || 0;
      articleCounts.set(article.articleId, count + 1);
    });

    const duplicates: Array<{ name: string, count: number }> = [];
    articleCounts.forEach((count, articleId) => {
      if (count > 1) {
        const article = selectedArticles.find(a => a.articleId === articleId);
        if (article) {
          duplicates.push({ name: article.articleName, count });
        }
      }
    });

    return duplicates;
  };

  // Reset form
  const resetForm = () => {
    const defaultFormData: Partial<MasterEntryRecord> = { beneficiaryType: beneficiaryTypeFilter };
    // Set default quantity to 1 for public type
    if (beneficiaryTypeFilter === 'public') {
      defaultFormData.quantity = 1;
    }
    setFormData(defaultFormData);
    setErrors({});
    setEditingRecordId(null);
    setIsAadharVerified(false);
    setMatchedHistoryRecords([]);
  };

  // Initialize quantity to 1 when switching to public form mode
  useEffect(() => {
    if (isFormMode && beneficiaryTypeFilter === 'public' && !editingRecordId && (formData.quantity === undefined || formData.quantity === 0)) {
      setFormData(prev => ({ ...prev, quantity: 1 }));
    }
  }, [isFormMode, beneficiaryTypeFilter, editingRecordId]);

  // Initialize quantity to 1 when switching to public form mode
  useEffect(() => {
    if (isFormMode && beneficiaryTypeFilter === 'public' && !editingRecordId && formData.quantity === undefined) {
      setFormData(prev => ({ ...prev, quantity: 1 }));
    }
  }, [isFormMode, beneficiaryTypeFilter, editingRecordId]);

  // Handle Add button click
  const handleAdd = () => {
    resetForm();
    setIsFormMode(true);
  };

  // Handle Cancel
  const handleCancel = () => {
    resetForm();
    setIsFormMode(false);
  };

  // Handle row click to edit
  const handleRowClick = (record: MasterEntryRecord) => {
    setFormData(record);
    setEditingRecordId(record.id);
    setIsFormMode(true);
  };

  // Toggle row expansion - only one row can be expanded at a time
  const toggleRowExpansion = (recordId: string) => {
    const newExpanded = new Set<string>();
    if (!expandedRows.has(recordId)) {
      // Only expand the clicked row
      newExpanded.add(recordId);
    }
    // If clicking the same row, newExpanded will be empty (collapses)
    setExpandedRows(newExpanded);
  };

  // Handle delete
  const handleDelete = async (e: React.MouseEvent, recordId: string) => {
    e.stopPropagation();
    setConfirmDialog({
      isOpen: true,
      title: 'Delete Record',
      message: 'Are you sure you want to delete this record?',
      type: 'danger',
      onConfirm: async () => {
        setConfirmDialog({ ...confirmDialog, isOpen: false });
        await handleDeleteConfirmed(recordId);
      },
    });
  };

  const handleDeleteConfirmed = async (recordId: string) => {
    setIsDeleting(true);
    try {
      // For district type, delete from database
      if (beneficiaryTypeFilter === 'district') {
        try {
          const record = records.find((r) => r.id === recordId);
          if (record && record.applicationNumber) {
            await deleteDistrictBeneficiaryEntriesByApplicationNumber(record.applicationNumber);

            // Refresh records from database
            try {
              const dbRecords = await fetchDistrictBeneficiaryEntriesGrouped();
              setRecords(dbRecords);
            } catch (refreshError) {
              console.error('Failed to refresh records after delete:', refreshError);
              // Remove from local state as fallback
              setRecords(records.filter((r) => r.id !== recordId));
            }
          } else {
            showError('Record not found or missing application number.');
          }
        } catch (error: any) {
          console.error('Failed to delete district entry:', error);
          showError(error.message || 'Failed to delete record. Please try again.');
        }
      } else if (beneficiaryTypeFilter === 'public') {
        // Delete from database for public type
        try {
        // Get entry details before deletion for audit log
        const { data: entryData } = await supabase
          .from('public_beneficiary_entries')
          .select('application_number, name, aadhar_number, article_id, quantity, total_amount, gender, female_status, address, mobile, is_handicapped, notes')
          .eq('id', recordId)
          .single();

        const { error } = await supabase
          .from('public_beneficiary_entries')
          .delete()
          .eq('id', recordId);

        if (error) throw error;

        // Log audit action for DELETE
        try {
          await logAction(user?.id || null, 'DELETE', 'public_beneficiary', entryData?.application_number || recordId, {
            entity_name: entryData?.application_number || recordId,
            entity_summary: `Public Beneficiary Entry: ${entryData?.application_number || recordId}`,
            deleted_values: entryData ? {
              id: recordId,
              application_number: entryData.application_number,
              name: entryData.name,
              aadhar_number: entryData.aadhar_number,
              article_id: entryData.article_id,
              quantity: entryData.quantity,
              total_amount: entryData.total_amount,
              gender: entryData.gender,
              female_status: entryData.female_status,
              address: entryData.address,
              mobile: entryData.mobile,
              is_handicapped: entryData.is_handicapped,
              notes: entryData.notes,
            } : {
              id: recordId,
            },
          });
        } catch (auditError) {
          console.error('Failed to log audit action for DELETE:', auditError);
          // Don't throw - audit logging should not break the main flow
        }

        // Refresh records from database
        const { data, error: fetchError } = await supabase
          .from('public_beneficiary_entries')
          .select(`
            id,
            application_number,
            name,
            aadhar_number,
            is_handicapped,
            gender,
            female_status,
            address,
            mobile,
            article_id,
            quantity,
            total_amount,
            notes,
            status,
            created_at
          `)
          .order('created_at', { ascending: false });

        if (fetchError) throw fetchError;

        const publicRecords: MasterEntryRecord[] = (data || []).map((entry: any) => ({
          id: entry.id,
          applicationNumber: entry.application_number || '',
          beneficiaryType: 'public' as const,
          createdAt: entry.created_at,
          aadharNumber: entry.aadhar_number,
          name: entry.name,
          handicapped: entry.is_handicapped,
          gender: entry.gender as 'Male' | 'Female' | 'Transgender' | undefined,
          femaleStatus: entry.female_status as 'Single Mother' | 'Widow' | 'Married' | 'Unmarried' | undefined,
          address: entry.address,
          mobile: entry.mobile,
          articleId: entry.article_id,
          quantity: entry.quantity,
          costPerUnit: entry.quantity > 0 ? (entry.total_amount / entry.quantity) : 0,
          totalValue: entry.total_amount,
          comments: entry.notes || '',
        }));

          setRecords(publicRecords);
          // Show success only after both deletion and refresh succeed
          showSuccess('Entry deleted successfully');
        } catch (error: any) {
          console.error('Failed to delete public entry:', error);
          showError(error.message || 'Failed to delete record. Please try again.');
        }
      } else if (beneficiaryTypeFilter === 'institutions') {
        // Delete from database for institutions type
        try {
          const record = records.find((r) => r.id === recordId);
          if (record && record.applicationNumber) {
            await deleteInstitutionBeneficiaryEntriesByApplicationNumber(record.applicationNumber);

            // Refresh records from database
            try {
              const dbRecords = await fetchInstitutionBeneficiaryEntriesGrouped();
              setRecords(dbRecords);
              // Show success only after both deletion and refresh succeed
              showSuccess('Entry deleted successfully');
            } catch (refreshError) {
              console.error('Failed to refresh records after delete:', refreshError);
              // Remove from local state as fallback
              setRecords(records.filter((r) => r.id !== recordId));
              // Still show success since deletion worked, but log the refresh error
              showSuccess('Entry deleted successfully');
            }
          } else {
            showError('Record not found or missing application number.');
          }
        } catch (error: any) {
          console.error('Failed to delete institution entry:', error);
          showError(error.message || 'Failed to delete record. Please try again.');
        }
      }
    } finally {
      setIsDeleting(false);
    }
  };

  // Validate form
  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (formData.beneficiaryType === 'district') {
      if (!formData.districtId) {
        newErrors.districtId = 'District is required';
      }
      if (!formData.selectedArticles || formData.selectedArticles.length === 0) {
        newErrors.selectedArticles = 'At least one article is required';
      } else {
        // Check if any article has cost 0
        const hasZeroCost = formData.selectedArticles.some(article => article.costPerUnit <= 0);
        if (hasZeroCost) {
          newErrors.selectedArticles = 'All articles must have a cost greater than 0';
        }
      }
    } else if (formData.beneficiaryType === 'public') {
      if (!formData.aadharNumber || formData.aadharNumber.length !== 12) {
        newErrors.aadharNumber = 'Aadhar number must be 12 digits';
      }
      if (!formData.name) {
        newErrors.name = 'Name is required';
      }
      if (!formData.gender) {
        newErrors.gender = 'Gender is required';
      }
      if (!formData.mobile) {
        newErrors.mobile = 'Valid mobile number is required';
      } else {
        // Validate &-separated mobile numbers
        const mobileNumbers = formData.mobile.split('&').map(num => num.trim()).filter(num => num.length > 0);
        if (mobileNumbers.length === 0) {
          newErrors.mobile = 'At least one mobile number is required';
        } else {
          // Check if all numbers are valid (10 digits)
          const invalidNumbers = mobileNumbers.filter(num => num.length !== 10 || !/^\d{10}$/.test(num));
          if (invalidNumbers.length > 0) {
            newErrors.mobile = 'All mobile numbers must be exactly 10 digits';
          }
        }
      }
      if (!formData.articleId) {
        newErrors.articleId = 'Article is required';
      }
      // Check quantity - use 1 as default if not set
      const quantity = formData.quantity || 1;
      if (quantity <= 0) {
        newErrors.quantity = 'Valid quantity is required';
      }
      if (formData.costPerUnit !== undefined && formData.costPerUnit <= 0) {
        newErrors.costPerUnit = 'Cost per unit must be greater than 0';
      }
    } else if (formData.beneficiaryType === 'institutions') {
      if (!formData.institutionName) {
        newErrors.institutionName = 'Name is required';
      }
      if (!formData.institutionType) {
        newErrors.institutionType = 'Institution type is required';
      }
      if (!formData.selectedArticles || formData.selectedArticles.length === 0) {
        newErrors.selectedArticles = 'At least one article is required';
      } else {
        // Check if any article has cost 0
        const hasZeroCost = formData.selectedArticles.some(article => article.costPerUnit <= 0);
        if (hasZeroCost) {
          newErrors.selectedArticles = 'All articles must have a cost greater than 0';
        }
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  // Calculate total accrued
  const calculateTotalAccrued = (): number => {
    if (formData.beneficiaryType === 'public') {
      return formData.totalValue || 0;
    } else if (
      formData.beneficiaryType === 'district' ||
      formData.beneficiaryType === 'institutions'
    ) {
      return (
        formData.selectedArticles?.reduce((sum, article) => sum + article.totalValue, 0) || 0
      );
    }
    return 0;
  };

  // Normalize Aadhar number (remove spaces and special characters)
  const normalizeAadharNumber = (aadhar: string): string => {
    if (!aadhar || typeof aadhar !== 'string') {
      console.log('[normalizeAadharNumber] Invalid input:', { aadhar, type: typeof aadhar });
      return '';
    }
    const normalized = aadhar.replace(/\D/g, '');
    console.log('[normalizeAadharNumber]', { 
      original: aadhar, 
      normalized, 
      originalLength: aadhar.length, 
      normalizedLength: normalized.length 
    });
    return normalized;
  };

  // Find existing aadhar entry in current public_beneficiary_entries table
  const findExistingAadharEntry = async (aadharNumber: string, excludeId?: string): Promise<MasterEntryRecord | null> => {
    const normalizedAadhar = normalizeAadharNumber(aadharNumber);
    
    let query = supabase
      .from('public_beneficiary_entries')
      .select(`
        id,
        application_number,
        name,
        aadhar_number,
        is_handicapped,
        address,
        mobile,
        article_id,
        quantity,
        total_amount,
        notes,
        status,
        created_at
      `);
    
    // Exclude current record if editing
    if (excludeId) {
      query = query.neq('id', excludeId);
    }
    
    const { data, error } = await query;
    
    if (error) {
      console.error('Error checking aadhar:', error);
      return null;
    }
    
    // Find record with matching normalized aadhar
    const existingRecord = (data || []).find(record => {
      const recordAadhar = normalizeAadharNumber(record.aadhar_number || '');
      return recordAadhar === normalizedAadhar;
    });
    
    if (!existingRecord) {
      return null;
    }
    
    // Transform to MasterEntryRecord format
    return {
      id: existingRecord.id,
      applicationNumber: existingRecord.application_number || '',
      beneficiaryType: 'public' as const,
      createdAt: existingRecord.created_at,
      aadharNumber: existingRecord.aadhar_number,
      name: existingRecord.name,
      handicapped: existingRecord.is_handicapped,
      address: existingRecord.address,
      mobile: existingRecord.mobile,
      articleId: existingRecord.article_id,
      quantity: existingRecord.quantity,
      costPerUnit: existingRecord.quantity > 0 ? (existingRecord.total_amount / existingRecord.quantity) : 0,
      totalValue: existingRecord.total_amount,
      comments: existingRecord.notes || '',
    };
  };

  // Handle Aadhar verification
  const handleVerifyAadhar = async () => {
    const aadharNumber = formData.aadharNumber;

    console.log('[handleVerifyAadhar] Starting verification', { 
      rawInput: aadharNumber, 
      inputLength: aadharNumber?.length 
    });

    if (!aadharNumber || aadharNumber.length !== 12) {
      console.log('[handleVerifyAadhar] Validation failed', { 
        aadharNumber, 
        length: aadharNumber?.length 
      });
      showError('Please enter a valid 12-digit Aadhar number');
      return;
    }

    try {
      setIsVerifyingAadhar(true);
      const normalizedAadhar = normalizeAadharNumber(aadharNumber);
      
      console.log('[handleVerifyAadhar] Normalized Aadhar', { 
        raw: aadharNumber, 
        normalized: normalizedAadhar,
        normalizedLength: normalizedAadhar.length
      });

      // Query public_beneficiary_history table
      // Fetch ALL records using pagination to handle Supabase's 1000 record limit
      console.log('[handleVerifyAadhar] Query strategy: Fetching all records with pagination');
      
      // Fetch all records using pagination (Supabase default limit is 1000)
      let allRecords: any[] = [];
      let page = 0;
      const pageSize = 1000;
      let hasMore = true;

      while (hasMore) {
        const from = page * pageSize;
        const to = from + pageSize - 1;
        
        console.log(`[handleVerifyAadhar] Fetching page ${page + 1} (records ${from} to ${to})`);
        
        const { data, error, count } = await supabase
          .from('public_beneficiary_history')
          .select('*', { count: 'exact' })
          .order('year', { ascending: false })
          .range(from, to);

        if (error) {
          console.error('[handleVerifyAadhar] Database query error:', error);
          showError('Failed to verify Aadhar number. Please try again.');
          return;
        }

        if (data && data.length > 0) {
          allRecords = allRecords.concat(data);
          console.log(`[handleVerifyAadhar] Page ${page + 1} fetched: ${data.length} records (total so far: ${allRecords.length})`);
          
          // Check if we've fetched all records
          if (data.length < pageSize || (count !== null && allRecords.length >= count)) {
            hasMore = false;
            console.log(`[handleVerifyAadhar] All records fetched. Total: ${allRecords.length} (count: ${count})`);
          } else {
            page++;
          }
        } else {
          hasMore = false;
        }
      }

      console.log('[handleVerifyAadhar] Query results', { 
        totalRecords: allRecords.length,
        sampleRecords: allRecords.slice(0, 3).map(r => ({
          id: r.id,
          aadhar_number: r.aadhar_number,
          aadhar_length: r.aadhar_number?.length,
          name: r.name,
          year: r.year
        }))
      });

      // Filter records by normalized Aadhar number (handles spaces, dashes, etc. in database)
      const matchedRecords: any[] = [];
      const unmatchedSamples: any[] = [];
      
      allRecords.forEach((record, index) => {
        const recordAadharRaw = record.aadhar_number || '';
        const recordAadharNormalized = normalizeAadharNumber(recordAadharRaw);
        
        // Log first few records for debugging
        if (index < 5) {
          console.log(`[handleVerifyAadhar] Record ${index + 1} comparison`, {
            recordId: record.id,
            raw: recordAadharRaw,
            normalized: recordAadharNormalized,
            normalizedLength: recordAadharNormalized.length,
            inputNormalized: normalizedAadhar,
            matches: recordAadharNormalized === normalizedAadhar
          });
        }
        
        if (recordAadharNormalized === normalizedAadhar) {
          matchedRecords.push(record);
        } else if (index < 10 && recordAadharNormalized.length === 12) {
          // Store sample of unmatched records for debugging
          unmatchedSamples.push({
            raw: recordAadharRaw,
            normalized: recordAadharNormalized,
            name: record.name
          });
        }
      });

      console.log('[handleVerifyAadhar] Matching complete', {
        totalRecords: allRecords.length,
        matchedCount: matchedRecords.length,
        normalizedInput: normalizedAadhar,
        unmatchedSamples: unmatchedSamples.slice(0, 5)
      });

      if (matchedRecords.length > 0) {
        console.log('[handleVerifyAadhar] Found matches', {
          count: matchedRecords.length,
          records: matchedRecords.map(r => ({
            name: r.name,
            year: r.year,
            aadhar: r.aadhar_number
          }))
        });
        // Aadhar exists in history - store matched records for display in form
        setIsAadharVerified(true);
        setMatchedHistoryRecords(matchedRecords);
      } else {
        console.log('[handleVerifyAadhar] No matches found', {
          normalizedInput: normalizedAadhar,
          totalRecordsChecked: allRecords.length,
          sampleUnmatched: unmatchedSamples.slice(0, 3)
        });
        // Aadhar doesn't exist - verification successful
        setIsAadharVerified(true);
        setMatchedHistoryRecords([]);
      }
    } catch (error: any) {
      console.error('[handleVerifyAadhar] Exception during verification:', error);
      showError(error.message || 'Failed to verify Aadhar number. Please try again.');
    } finally {
      setIsVerifyingAadhar(false);
    }
  };

  // Handle save for public entry (extracted for reuse)
  const handleSavePublicEntry = async (recordIdToUpdate?: string) => {
    const costPerUnit = formData.costPerUnit || 0;
    const quantity = formData.quantity || 1;
    const totalValue = costPerUnit * quantity;
    const updateRecordId = recordIdToUpdate || editingRecordId;

    try {
      if (updateRecordId) {
        // Fetch old values before update for audit log
        const { data: oldData } = await supabase
          .from('public_beneficiary_entries')
          .select('*')
          .eq('id', updateRecordId)
          .single();

        // Update existing record - use existing application number
        const updateData = {
          application_number: formData.applicationNumber,
          name: formData.name,
          aadhar_number: formData.aadharNumber,
          is_handicapped: formData.handicapped || false,
          gender: formData.gender || null,
          female_status: formData.gender === 'Female' ? formData.femaleStatus || null : null,
          address: formData.address,
          mobile: formData.mobile,
          article_id: formData.articleId,
          quantity: quantity,
          total_amount: totalValue,
          notes: formData.comments || null,
          updated_at: new Date().toISOString(),
        };

        const { error } = await supabase
          .from('public_beneficiary_entries')
          .update(updateData)
          .eq('id', updateRecordId);

        if (error) throw error;

        // Log audit action for UPDATE
        try {
          const updatedFields = Object.keys(updateData);
          const oldValues: Record<string, any> = {};
          const newValues: Record<string, any> = {};

          updatedFields.forEach((field) => {
            if (oldData) {
              oldValues[field] = oldData[field as keyof typeof oldData];
            }
            newValues[field] = updateData[field as keyof typeof updateData];
          });

          await logAction(user?.id || null, 'UPDATE', 'public_beneficiary', formData.applicationNumber || updateRecordId, {
            entity_name: formData.applicationNumber || updateRecordId,
            entity_summary: `Public Beneficiary Entry: ${formData.applicationNumber || updateRecordId}`,
            old_values: oldValues,
            new_values: newValues,
            updated_fields: updatedFields,
            affected_fields: updatedFields,
          });
        } catch (auditError) {
          console.error('Failed to log audit action for UPDATE:', auditError);
          // Don't throw - audit logging should not break the main flow
        }
      } else {
        // Create new record - generate new application number
        const applicationNumber = await generateApplicationNumberFromDB('public');
        const { error } = await supabase
          .from('public_beneficiary_entries')
          .insert({
            application_number: applicationNumber,
            name: formData.name,
            aadhar_number: formData.aadharNumber,
            is_handicapped: formData.handicapped || false,
            gender: formData.gender || null,
            female_status: formData.gender === 'Female' ? formData.femaleStatus || null : null,
            address: formData.address,
            mobile: formData.mobile,
            article_id: formData.articleId,
            quantity: quantity,
            total_amount: totalValue,
            notes: formData.comments || null,
            status: 'pending',
            created_by: user?.id || null,
          });

        if (error) throw error;

        // Log audit action for CREATE
        try {
          await logAction(user?.id || null, 'CREATE', 'public_beneficiary', applicationNumber, {
            entity_name: applicationNumber,
            entity_summary: `Public Beneficiary Entry: ${applicationNumber}`,
            new_values: {
              application_number: applicationNumber,
              name: formData.name,
              aadhar_number: formData.aadharNumber,
              article_id: formData.articleId,
              quantity: quantity,
              total_amount: totalValue,
              gender: formData.gender || null,
              female_status: formData.gender === 'Female' ? formData.femaleStatus || null : null,
              address: formData.address || null,
              mobile: formData.mobile || null,
              is_handicapped: formData.handicapped || false,
              notes: formData.comments || null,
            },
          });
        } catch (auditError) {
          console.error('Failed to log audit action for CREATE:', auditError);
          // Don't throw - audit logging should not break the main flow
        }

        // Refresh records from database
        const { data, error: fetchError } = await supabase
          .from('public_beneficiary_entries')
          .select(`
            id,
            application_number,
            name,
            aadhar_number,
            is_handicapped,
            gender,
            female_status,
            address,
            mobile,
            article_id,
            quantity,
            total_amount,
            notes,
            status,
            created_at
          `)
          .order('created_at', { ascending: false });

        if (fetchError) throw fetchError;

        const publicRecords: MasterEntryRecord[] = (data || []).map((entry: any) => ({
          id: entry.id,
          applicationNumber: entry.application_number || '',
          beneficiaryType: 'public' as const,
          createdAt: entry.created_at,
          aadharNumber: entry.aadhar_number,
          name: entry.name,
          handicapped: entry.is_handicapped,
          gender: entry.gender as 'Male' | 'Female' | 'Transgender' | undefined,
          femaleStatus: entry.female_status as 'Single Mother' | 'Widow' | 'Married' | 'Unmarried' | undefined,
          address: entry.address,
          mobile: entry.mobile,
          articleId: entry.article_id,
          quantity: entry.quantity,
          costPerUnit: entry.quantity > 0 ? (entry.total_amount / entry.quantity) : 0,
          totalValue: entry.total_amount,
          comments: entry.notes || '',
        }));

        setRecords(publicRecords);
        resetForm();
        setIsFormMode(false);
        // Scroll to top of page
        window.scrollTo({ top: 0, behavior: 'smooth' });
        // Show application number with name in popup for 5 seconds (greenish color)
        const displayName = formData.name || '';
        showSuccess(`Entry created successfully. ${applicationNumber}${displayName ? `-${displayName}` : ''}`, 5000);
        return;
      }

      // Refresh records from database
      const { data, error: fetchError } = await supabase
        .from('public_beneficiary_entries')
        .select(`
          id,
          application_number,
          name,
          aadhar_number,
          is_handicapped,
          gender,
          female_status,
          address,
          mobile,
          article_id,
          quantity,
          total_amount,
          notes,
          status,
          created_at
        `)
        .order('created_at', { ascending: false });

      if (fetchError) throw fetchError;

      const publicRecords: MasterEntryRecord[] = (data || []).map((entry: any) => ({
        id: entry.id,
        applicationNumber: entry.application_number || '',
        beneficiaryType: 'public' as const,
        createdAt: entry.created_at,
        aadharNumber: entry.aadhar_number,
        name: entry.name,
        handicapped: entry.is_handicapped,
        gender: entry.gender as 'Male' | 'Female' | 'Transgender' | undefined,
        femaleStatus: entry.female_status as 'Single Mother' | 'Widow' | 'Married' | 'Unmarried' | undefined,
        address: entry.address,
        mobile: entry.mobile,
        articleId: entry.article_id,
        quantity: entry.quantity,
        costPerUnit: entry.quantity > 0 ? (entry.total_amount / entry.quantity) : 0,
        totalValue: entry.total_amount,
        comments: entry.notes || '',
      }));

      setRecords(publicRecords);
      resetForm();
      setIsFormMode(false);
      // Scroll to top of page
      window.scrollTo({ top: 0, behavior: 'smooth' });
      showSuccess('Entry updated successfully');
    } catch (error: any) {
      console.error('Failed to save public entry:', error);
      showError(error.message || 'Failed to save entry. Please try again.');
    }
  };

  // Handle save
  const handleSave = async () => {
    if (!validateForm()) {
      return;
    }

    if (isSaving) {
      return; // Prevent multiple clicks
    }

    setSaving(true);

    // const totalAccrued = calculateTotalAccrued();
    // const now = new Date().toISOString();

    // For district type, save to database
    if (formData.beneficiaryType === 'district' && formData.districtId && formData.selectedArticles && formData.selectedArticles.length > 0) {
      try {
        let applicationNumber = formData.applicationNumber;

        // Track if this is an update (replacing existing entries)
        let isUpdate = false;
        let oldEntries: any[] = [];

        // If editing, use existing application number
        // If new, check district_master for application_number first
        if (!editingRecordId && !applicationNumber) {
          // First, check if district_master has an application_number
          const districtAppNumber = await getDistrictApplicationNumber(formData.districtId);
          
          if (districtAppNumber) {
            // Use application_number from district_master
            applicationNumber = districtAppNumber;
            // Delete old entries to replace with new ones (suppress audit log, will log as UPDATE)
            oldEntries = await deleteDistrictBeneficiaryEntriesByApplicationNumber(applicationNumber, true);
            isUpdate = oldEntries.length > 0;
          } else {
            // No application_number in district_master, check if district already has entries
            const existingEntry = await fetchDistrictBeneficiaryEntryByDistrictId(formData.districtId);
            if (existingEntry) {
              // District already has an entry, use its application number
              applicationNumber = existingEntry.applicationNumber;
              // Delete old entries to replace with new ones (suppress audit log, will log as UPDATE)
              if (applicationNumber) {
                oldEntries = await deleteDistrictBeneficiaryEntriesByApplicationNumber(applicationNumber, true);
                isUpdate = oldEntries.length > 0;
              }
            } else {
              // New district entry, generate new application number
              applicationNumber = await generateApplicationNumberFromDB('district');
              // Update district_master with the new application number
              await updateDistrictApplicationNumber(formData.districtId, applicationNumber);
            }
          }
        } else if (editingRecordId && applicationNumber) {
          // Editing existing entry - delete old entries first (suppress audit log, will log as UPDATE)
          oldEntries = await deleteDistrictBeneficiaryEntriesByApplicationNumber(applicationNumber, true);
          isUpdate = oldEntries.length > 0;
        }

        if (!applicationNumber) {
          showError('Failed to generate application number. Please try again.');
          return;
        }

        // Create one entry per article
        const entries = formData.selectedArticles.map((article) => ({
          district_id: formData.districtId!,
          application_number: applicationNumber,
          article_id: article.articleId,
          quantity: article.quantity,
          article_cost_per_unit: article.costPerUnit,
          total_amount: article.totalValue,
          notes: article.comments || null,
          status: 'pending' as const,
        }));

        await createDistrictBeneficiaryEntries(entries, isUpdate, oldEntries);

        // Update district_master table with application_number (if not already set)
        // This ensures district_master always has the application_number
        try {
          const currentDistrictAppNumber = await getDistrictApplicationNumber(formData.districtId!);
          if (!currentDistrictAppNumber) {
            await updateDistrictApplicationNumber(formData.districtId!, applicationNumber);
          }
        } catch (updateError) {
          console.error('Failed to update district_master application_number:', updateError);
          // Don't fail the entire save if this update fails - log error but continue
        }

        // Refresh records from database
        try {
          const dbRecords = await fetchDistrictBeneficiaryEntriesGrouped();
          setRecords(dbRecords);
        } catch (refreshError) {
          console.error('Failed to refresh records after save:', refreshError);
          // Continue anyway - the save was successful
        }

        resetForm();
        setIsFormMode(false);
        setSaving(false);
        // Scroll to top of page
        window.scrollTo({ top: 0, behavior: 'smooth' });
        // District entries don't show popup with application number
        return;
      } catch (error: any) {
        console.error('Failed to save district entry:', error);
        showError(error.message || 'Failed to save district entry. Please try again.');
        setSaving(false);
        return;
      }
    }

    // For public type, save to database
    if (formData.beneficiaryType === 'public') {
      // Check if Aadhar has been verified
      if (!isAadharVerified) {
        showError('Please verify the Aadhar number before saving.');
        setSaving(false);
        return;
      }

      // Check for duplicate aadhar in current entries
      const existingEntry = await findExistingAadharEntry(
        formData.aadharNumber || '',
        editingRecordId || undefined
      );

      if (existingEntry) {
        // Show confirmation dialog with side-by-side comparison
        const existingArticleName = getArticleById(existingEntry.articleId || '')?.name || 'Unknown';
        const newArticleName = getArticleById(formData.articleId || '')?.name || 'Unknown';
        const newQuantity = formData.quantity || 1;
        const newCostPerUnit = formData.costPerUnit ?? (formData.articleId ? getArticleById(formData.articleId)?.costPerUnit : 0) ?? 0;
        const newTotalValue = newCostPerUnit * newQuantity;
        
        const comparisonDetails = (
          <div className="space-y-4">
            <p className="text-sm font-medium text-gray-900 dark:text-white mb-3">
              This Aadhar number already exists in the current entries. Compare the records below:
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Existing Record */}
              <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 border-2 border-blue-200 dark:border-blue-800">
                <h4 className="text-sm font-semibold text-blue-900 dark:text-blue-100 mb-3 flex items-center gap-2">
                  <span className="w-2 h-2 bg-blue-600 rounded-full"></span>
                  Existing Record
                </h4>
                <div className="grid grid-cols-1 gap-2 text-sm">
                  <div className="flex flex-col">
                    <span className="font-medium text-gray-700 dark:text-gray-300 text-xs">Application Number:</span>
                    <span className="text-gray-900 dark:text-white">{existingEntry.applicationNumber}</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="font-medium text-gray-700 dark:text-gray-300 text-xs">Name:</span>
                    <span className="text-gray-900 dark:text-white">{existingEntry.name}</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="font-medium text-gray-700 dark:text-gray-300 text-xs">Aadhar:</span>
                    <span className="text-gray-900 dark:text-white">{existingEntry.aadharNumber}</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="font-medium text-gray-700 dark:text-gray-300 text-xs">Article:</span>
                    <span className="text-gray-900 dark:text-white">{existingArticleName}</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="font-medium text-gray-700 dark:text-gray-300 text-xs">Quantity:</span>
                    <span className="text-gray-900 dark:text-white">{existingEntry.quantity}</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="font-medium text-gray-700 dark:text-gray-300 text-xs">Cost Per Unit:</span>
                    <span className="text-gray-900 dark:text-white">
                      {CURRENCY_SYMBOL}{(existingEntry.costPerUnit || 0).toLocaleString('en-IN')}
                    </span>
                  </div>
                  <div className="flex flex-col">
                    <span className="font-medium text-gray-700 dark:text-gray-300 text-xs">Total Amount:</span>
                    <span className="text-gray-900 dark:text-white font-semibold">
                      {CURRENCY_SYMBOL}{(existingEntry.totalValue || 0).toLocaleString('en-IN')}
                    </span>
                  </div>
                  {existingEntry.address && (
                    <div className="flex flex-col">
                      <span className="font-medium text-gray-700 dark:text-gray-300 text-xs">Address:</span>
                      <span className="text-gray-900 dark:text-white">{existingEntry.address}</span>
                    </div>
                  )}
                  {existingEntry.mobile && (
                    <div className="flex flex-col">
                      <span className="font-medium text-gray-700 dark:text-gray-300 text-xs">Mobile:</span>
                      <span className="text-gray-900 dark:text-white">{existingEntry.mobile}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* New Record */}
              <div className="bg-yellow-50 dark:bg-yellow-900/20 rounded-lg p-4 border-2 border-yellow-200 dark:border-yellow-800">
                <h4 className="text-sm font-semibold text-yellow-900 dark:text-yellow-100 mb-3 flex items-center gap-2">
                  <span className="w-2 h-2 bg-yellow-600 rounded-full"></span>
                  New Record (You're Entering)
                </h4>
                <div className="grid grid-cols-1 gap-2 text-sm">
                  <div className="flex flex-col">
                    <span className="font-medium text-gray-700 dark:text-gray-300 text-xs">Application Number:</span>
                    <span className="text-gray-900 dark:text-white">-</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="font-medium text-gray-700 dark:text-gray-300 text-xs">Name:</span>
                    <span className="text-gray-900 dark:text-white">{formData.name || '-'}</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="font-medium text-gray-700 dark:text-gray-300 text-xs">Aadhar:</span>
                    <span className="text-gray-900 dark:text-white">{formData.aadharNumber || '-'}</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="font-medium text-gray-700 dark:text-gray-300 text-xs">Article:</span>
                    <span className="text-gray-900 dark:text-white">{newArticleName}</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="font-medium text-gray-700 dark:text-gray-300 text-xs">Quantity:</span>
                    <span className="text-gray-900 dark:text-white">{newQuantity}</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="font-medium text-gray-700 dark:text-gray-300 text-xs">Cost Per Unit:</span>
                    <span className="text-gray-900 dark:text-white">
                      {CURRENCY_SYMBOL}{newCostPerUnit.toLocaleString('en-IN')}
                    </span>
                  </div>
                  <div className="flex flex-col">
                    <span className="font-medium text-gray-700 dark:text-gray-300 text-xs">Total Amount:</span>
                    <span className="text-gray-900 dark:text-white font-semibold">
                      {CURRENCY_SYMBOL}{newTotalValue.toLocaleString('en-IN')}
                    </span>
                  </div>
                  {formData.address && (
                    <div className="flex flex-col">
                      <span className="font-medium text-gray-700 dark:text-gray-300 text-xs">Address:</span>
                      <span className="text-gray-900 dark:text-white">{formData.address}</span>
                    </div>
                  )}
                  {formData.mobile && (
                    <div className="flex flex-col">
                      <span className="font-medium text-gray-700 dark:text-gray-300 text-xs">Mobile:</span>
                      <span className="text-gray-900 dark:text-white">{formData.mobile}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
            <p className="text-sm text-gray-700 dark:text-gray-300 mt-3">
              Choose an option below to proceed.
            </p>
          </div>
        );
        
        // Store current form data to use for update
        const currentFormData = { ...formData };
        
        setConfirmDialog({
          isOpen: true,
          title: 'Aadhar Number Already Exists',
          message: comparisonDetails,
          type: 'warning',
          confirmText: 'Update with New Values',
          secondaryText: 'Edit Existing Record',
          onConfirm: async () => {
            setConfirmDialog({ ...confirmDialog, isOpen: false });
            // Update existing record with new values directly
            // Set formData with new values but keep existing application number and id
            const updatedFormData = {
              ...currentFormData,
              id: existingEntry.id,
              applicationNumber: existingEntry.applicationNumber,
            };
            setFormData(updatedFormData);
            setEditingRecordId(existingEntry.id);
            setIsAadharVerified(true);
            setMatchedHistoryRecords([]);
            // Now save with the new values - pass recordId directly to avoid async state issues
            try {
              // Use a temporary function that uses the updated formData
              const costPerUnit = updatedFormData.costPerUnit || 0;
              const quantity = updatedFormData.quantity || 1;
              const totalValue = costPerUnit * quantity;

              // Update existing record directly
              const { error } = await supabase
                .from('public_beneficiary_entries')
                .update({
                  application_number: existingEntry.applicationNumber,
                  name: updatedFormData.name,
                  aadhar_number: updatedFormData.aadharNumber,
                  is_handicapped: updatedFormData.handicapped || false,
                  gender: updatedFormData.gender || null,
                  female_status: updatedFormData.gender === 'Female' ? updatedFormData.femaleStatus || null : null,
                  address: updatedFormData.address,
                  mobile: updatedFormData.mobile,
                  article_id: updatedFormData.articleId,
                  quantity: quantity,
                  total_amount: totalValue,
                  notes: updatedFormData.comments || null,
                  updated_at: new Date().toISOString(),
                })
                .eq('id', existingEntry.id);

              if (error) throw error;

              // Refresh records from database
              const { data, error: fetchError } = await supabase
                .from('public_beneficiary_entries')
                .select(`
                  id,
                  application_number,
                  name,
                  aadhar_number,
                  is_handicapped,
                  gender,
                  female_status,
                  address,
                  mobile,
                  article_id,
                  quantity,
                  total_amount,
                  notes,
                  status,
                  created_at
                `)
                .order('created_at', { ascending: false });

              if (fetchError) throw fetchError;

              const publicRecords: MasterEntryRecord[] = (data || []).map((entry: any) => ({
                id: entry.id,
                applicationNumber: entry.application_number || '',
                beneficiaryType: 'public' as const,
                createdAt: entry.created_at,
                aadharNumber: entry.aadhar_number,
                name: entry.name,
                handicapped: entry.is_handicapped,
                gender: entry.gender as 'Male' | 'Female' | 'Transgender' | undefined,
                femaleStatus: entry.female_status as 'Single Mother' | 'Widow' | 'Married' | 'Unmarried' | undefined,
                address: entry.address,
                mobile: entry.mobile,
                articleId: entry.article_id,
                quantity: entry.quantity,
                costPerUnit: entry.quantity > 0 ? (entry.total_amount / entry.quantity) : 0,
                totalValue: entry.total_amount,
                comments: entry.notes || '',
              }));

              setRecords(publicRecords);
              resetForm();
              setIsFormMode(false);
              showSuccess('Entry updated successfully');
            } catch (error: any) {
              console.error('Failed to update public entry:', error);
              showError(error.message || 'Failed to update entry. Please try again.');
            } finally {
              setSaving(false);
            }
          },
          onSecondary: () => {
            setConfirmDialog({ ...confirmDialog, isOpen: false });
            // Load existing record into form for editing
            setFormData(existingEntry);
            setEditingRecordId(existingEntry.id);
            setIsAadharVerified(true);
            setMatchedHistoryRecords([]);
            setSaving(false);
          },
        });
        setSaving(false);
        return;
      }

      // Check if there are matched history records
      if (matchedHistoryRecords.length > 0) {
        // Extract unique years from matched records
        const years = [...new Set(matchedHistoryRecords.map(record => record.year).filter(Boolean))].sort((a, b) => b - a);
        const yearsText = years.length > 0 ? years.join(', ') : 'previous year(s)';

        // Show confirmation dialog
        setConfirmDialog({
          isOpen: true,
          title: 'Confirm Adding Public Data',
          message: `This Aadhar number has already received benefits in year(s): ${yearsText}. Are you sure you want to add public data for the same Aadhar number?`,
          type: 'warning',
          onConfirm: async () => {
            setConfirmDialog({ ...confirmDialog, isOpen: false });
            try {
              await handleSavePublicEntry();
            } finally {
              setSaving(false);
            }
          },
        });
        // Don't set saving to false here - it will be set in the onConfirm callback
        return;
      }

      // No matched records, proceed with save directly
      try {
        await handleSavePublicEntry();
      } finally {
        setSaving(false);
      }
      return;
    }

    // For institutions type, save to database
    if (formData.beneficiaryType === 'institutions') {
      if (!formData.selectedArticles || formData.selectedArticles.length === 0) {
        showError('Please select at least one article.');
        setSaving(false);
        return;
      }

      if (!formData.institutionName) {
        showError('Institution name is required.');
        setSaving(false);
        return;
      }

      if (!formData.institutionType) {
        showError('Institution type is required.');
        setSaving(false);
        return;
      }

      try {
        let applicationNumber = formData.applicationNumber;

        if (!editingRecordId && !applicationNumber) {
          // New institution entry, generate new application number
          applicationNumber = await generateApplicationNumberFromDB('institutions');
        } else if (editingRecordId && applicationNumber) {
          // Editing existing entry - delete old entries first
          await deleteInstitutionBeneficiaryEntriesByApplicationNumber(applicationNumber);
        }

        if (!applicationNumber) {
          showError('Failed to generate application number. Please try again.');
          setSaving(false);
          return;
        }

        // Create one entry per article
        const entries = formData.selectedArticles.map((article) => ({
          institution_name: formData.institutionName!,
          institution_type: formData.institutionType!,
          application_number: applicationNumber,
          address: formData.address || null,
          mobile: formData.mobile || null,
          article_id: article.articleId,
          quantity: article.quantity,
          article_cost_per_unit: article.costPerUnit,
          total_amount: article.totalValue,
          notes: article.comments || null,
          status: 'pending' as const,
          created_by: user?.id || undefined,
        }));

        await createInstitutionBeneficiaryEntries(entries);

        // Refresh records from database
        try {
          const dbRecords = await fetchInstitutionBeneficiaryEntriesGrouped();
          setRecords(dbRecords);
        } catch (refreshError) {
          console.error('Failed to refresh records after save:', refreshError);
          // Continue anyway - the save was successful
        }

        resetForm();
        setIsFormMode(false);
        // Scroll to top of page
        window.scrollTo({ top: 0, behavior: 'smooth' });
        if (editingRecordId) {
          showSuccess('Entry updated successfully');
        } else {
          // Show application number with name in popup for 8 seconds for new entries (greenish color)
          const displayName = formData.institutionName || '';
          showSuccess(`Entry created successfully. ${applicationNumber}${displayName ? `-${displayName}` : ''}`, 8000);
        }
        setSaving(false);
        return;
      } catch (error: any) {
        console.error('Failed to save institution entry:', error);
        showError(error.message || 'Failed to save institution entry. Please try again.');
        setSaving(false);
        return;
      }
    }
  };

  const handleExportClick = () => {
    setShowExportModal(true);
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      // Fetch all articles to get item_type and article_name_tk
      const allArticlesData = await fetchAllArticles(true);
      const articleMap = new Map<string, ArticleRecord>();
      allArticlesData.forEach(article => {
        articleMap.set(article.id, article);
      });

      // Determine which types to export
      const typesToExport: ('district' | 'public' | 'institutions')[] = 
        exportType === 'all' 
          ? ['district', 'public', 'institutions']
          : [exportType];

      const allExportData: any[] = [];

      // Export District
      if (typesToExport.includes('district')) {
        const districtRecords = await fetchDistrictBeneficiaryEntriesGrouped();
        // Fetch districts to get president mobile numbers
        const districtsList = await fetchDistricts();
        const districtMap = new Map(districtsList.map(d => [d.id, d]));
        
        const districtData = districtRecords.flatMap((record) => {
          const district = record.districtId ? districtMap.get(record.districtId) : null;
          const presidentMobile = district?.mobileNumber || '';
          
          if (!record.selectedArticles || record.selectedArticles.length === 0) {
            return [{
              'Application Number': record.applicationNumber || '',
              'Beneficiary Name': record.districtName || '',
              'Requested Item': '',
              'Quantity': 0,
              'Cost Per Unit': 0,
              'Total Value': 0,
              'Address': record.districtName || '',
              'Mobile': presidentMobile,
              'Aadhar Number': '',
              'Handicapped Status': '',
              'Gender': '',
              'Gender Category': '',
              'Beneficiary Type': 'District',
              'Item Type': '',
              'Article Category': '',
              'Super Category Article': '',
              'Requested Item Tk': '',
              'Comments': '',
            }];
          }
          return record.selectedArticles.map((article) => {
            const articleData = articleMap.get(article.articleId);
            return {
              'Application Number': record.applicationNumber || '',
              'Beneficiary Name': record.districtName || '',
              'Requested Item': article.articleName || '',
              'Quantity': article.quantity || 0,
              'Cost Per Unit': article.costPerUnit || articleData?.cost_per_unit || 0,
              'Total Value': article.totalValue || 0,
              'Address': record.districtName || '',
              'Mobile': presidentMobile,
              'Aadhar Number': '',
              'Handicapped Status': '',
              'Gender': '',
              'Gender Category': '',
              'Beneficiary Type': 'District',
              'Item Type': articleData?.item_type || '',
              'Article Category': articleData?.category || '',
              'Super Category Article': articleData?.master_category || '',
              'Requested Item Tk': articleData?.article_name_tk || '',
              'Comments': article.comments || '',
            };
          });
        });
        allExportData.push(...districtData);
      }

      // Export Public
      if (typesToExport.includes('public')) {
        const { data: publicData, error: publicError } = await supabase
          .from('public_beneficiary_entries')
          .select(`
            id,
            application_number,
            name,
            aadhar_number,
            is_handicapped,
            gender,
            female_status,
            address,
            mobile,
            article_id,
            quantity,
            total_amount,
            notes,
            status,
            created_at
          `)
          .order('created_at', { ascending: false });

        if (publicError) {
          showError('Failed to load public records for export.');
          setExporting(false);
          return;
        }

        const publicExportData = (publicData || []).map((entry: any) => {
          const articleData = articleMap.get(entry.article_id);
          return {
            'Application Number': entry.application_number || '',
            'Beneficiary Name': entry.name || '',
            'Requested Item': articleData?.article_name || '',
            'Quantity': entry.quantity || 0,
            'Cost Per Unit': articleData?.cost_per_unit || (entry.quantity > 0 ? (entry.total_amount / entry.quantity) : 0),
            'Total Value': entry.total_amount || 0,
            'Address': entry.address || '',
            'Mobile': entry.mobile || '',
            'Aadhar Number': entry.aadhar_number || '',
            'Handicapped Status': entry.is_handicapped ? 'Yes' : 'No',
            'Gender': entry.gender || '',
            'Gender Category': entry.gender === 'Female' ? (entry.female_status || '') : '',
            'Beneficiary Type': 'Public',
            'Item Type': articleData?.item_type || '',
            'Article Category': articleData?.category || '',
            'Super Category Article': articleData?.master_category || '',
            'Requested Item Tk': articleData?.article_name_tk || '',
            'Comments': entry.notes || '',
          };
        });
        allExportData.push(...publicExportData);
      }

      // Export Institutions
      if (typesToExport.includes('institutions')) {
        const institutionsRecords = await fetchInstitutionBeneficiaryEntriesGrouped();
        const institutionsData = institutionsRecords.flatMap((record) => {
          if (!record.selectedArticles || record.selectedArticles.length === 0) {
            return [{
              'Application Number': record.applicationNumber || '',
              'Beneficiary Name': record.institutionName || '',
              'Requested Item': '',
              'Quantity': 0,
              'Cost Per Unit': 0,
              'Total Value': 0,
              'Address': record.address || '',
              'Mobile': record.mobile || '',
              'Aadhar Number': '',
              'Handicapped Status': '',
              'Gender': '',
              'Gender Category': '',
              'Beneficiary Type': record.institutionType === 'others' ? 'Others' : 'Institutions',
              'Item Type': '',
              'Article Category': '',
              'Super Category Article': '',
              'Requested Item Tk': '',
              'Comments': '',
            }];
          }
          return record.selectedArticles.map((article) => {
            const articleData = articleMap.get(article.articleId);
            return {
              'Application Number': record.applicationNumber || '',
              'Beneficiary Name': record.institutionName || '',
              'Requested Item': article.articleName || '',
              'Quantity': article.quantity || 0,
              'Cost Per Unit': article.costPerUnit || articleData?.cost_per_unit || (article.quantity > 0 ? (article.totalValue / article.quantity) : 0),
              'Total Value': article.totalValue || 0,
              'Address': record.address || '',
              'Mobile': record.mobile || '',
              'Aadhar Number': '',
              'Handicapped Status': '',
              'Gender': '',
              'Gender Category': '',
              'Beneficiary Type': record.institutionType === 'others' ? 'Others' : 'Institutions',
              'Item Type': articleData?.item_type || '',
              'Article Category': articleData?.category || '',
              'Super Category Article': articleData?.master_category || '',
              'Requested Item Tk': articleData?.article_name_tk || '',
              'Comments': article.comments || '',
            };
          });
        });
        allExportData.push(...institutionsData);
      }

      // Export all data with consolidated fields
      if (allExportData.length > 0) {
        const filename = exportType === 'all' 
          ? 'master-entry-all' 
          : `master-entry-${exportType}`;
        
        exportToCSV(allExportData, filename, [
          'Application Number',
          'Beneficiary Name',
          'Requested Item',
          'Quantity',
          'Cost Per Unit',
          'Total Value',
          'Address',
          'Mobile',
          'Aadhar Number',
          'Handicapped Status',
          'Gender',
          'Gender Category',
          'Beneficiary Type',
          'Item Type',
          'Article Category',
          'Super Category Article',
          'Requested Item Tk',
          'Comments',
        ], showWarning);

        // Log export action
        if (user) {
          await logAction(user.id, 'EXPORT', 'master_entry', null, {
            exported_type: exportType,
            exported_count: allExportData.length,
          });
        }

        setShowExportModal(false);
        setExportType('all');
        showSuccess(`Exported ${allExportData.length} record(s) successfully`);
      } else {
        showWarning('No data to export.');
      }
    } catch (error) {
      console.error('Error exporting master entries:', error);
      showError('Failed to export data. Please try again.');
    } finally {
      setExporting(false);
    }
  };

  // Fetch existing entries for selected district to calculate remaining fund
  useEffect(() => {
    const loadExistingEntries = async () => {
      if (formData.districtId && formData.beneficiaryType === 'district' && isFormMode) {
        try {
          setLoadingExistingEntries(true);
          const entries = await fetchDistrictBeneficiaryEntries(formData.districtId);
          // Calculate total from existing entries (excluding current editing record if editing)
          let total = entries.reduce((sum, entry) => {
            const amount = typeof entry.total_amount === 'string'
              ? parseFloat(entry.total_amount)
              : (entry.total_amount || 0);
            return sum + amount;
          }, 0);

          // If editing, subtract the current record's total from existing entries
          if (editingRecordId) {
            const currentRecord = records.find(r => r.id === editingRecordId);
            if (currentRecord && currentRecord.totalAccrued) {
              total -= currentRecord.totalAccrued;
            }
          }

          setExistingDistrictEntriesTotal(total);
        } catch (error) {
          console.error('Failed to load existing entries for remaining fund calculation:', error);
          setExistingDistrictEntriesTotal(0);
        } finally {
          setLoadingExistingEntries(false);
        }
      } else {
        setExistingDistrictEntriesTotal(0);
      }
    };

    loadExistingEntries();
  }, [formData.districtId, formData.beneficiaryType, isFormMode, editingRecordId, records]);

  // District form
  const renderDistrictForm = () => {
    const selectedDistrict = formData.districtId
      ? getDistrictById(formData.districtId)
      : null;

    // Calculate current form total from selected articles
    const currentFormTotal = formData.selectedArticles?.reduce(
      (sum, article) => sum + article.totalValue,
      0
    ) || 0;

    // Calculate remaining fund: Allotted - (Existing DB entries + Current form selection)
    const remainingFund = selectedDistrict
      ? selectedDistrict.allottedBudget - existingDistrictEntriesTotal - currentFormTotal
      : 0;

    return (
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            District Name <span className="text-red-500">*</span>
          </label>
          <select
            value={formData.districtId || ''}
            onChange={async (e) => {
              const districtId = e.target.value;
              const district = getDistrictById(districtId);

              // Check if this district already has an entry
              if (districtId && !editingRecordId) {
                try {
                  const existingEntry = await fetchDistrictBeneficiaryEntryByDistrictId(districtId);
                  if (existingEntry) {
                    // District already has an entry, load it for editing
                    setFormData({
                      ...existingEntry,
                      beneficiaryType: 'district',
                    });
                    setEditingRecordId(existingEntry.id);
                  } else {
                    // New district, reset form
                    setFormData({
                      ...formData,
                      districtId: districtId,
                      districtName: district?.name,
                      selectedArticles: [],
                    });
                    setEditingRecordId(null);
                  }
                } catch (error) {
                  console.error('Error checking existing district entry:', error);
                  // On error, just set the district
                  setFormData({
                    ...formData,
                    districtId: districtId,
                    districtName: district?.name,
                  });
                }
              } else {
                // If editing, check if new district has an entry
                if (districtId) {
                  try {
                    const existingEntry = await fetchDistrictBeneficiaryEntryByDistrictId(districtId);
                    if (existingEntry) {
                      // New district has an entry, load it
                      setFormData({
                        ...existingEntry,
                        beneficiaryType: 'district',
                      });
                      setEditingRecordId(existingEntry.id);
                    } else {
                      // New district has no entry, clear selected articles
                      setFormData({
                        ...formData,
                        districtId: districtId,
                        districtName: district?.name,
                        selectedArticles: [],
                      });
                      setEditingRecordId(null);
                    }
                  } catch (error) {
                    console.error('Error checking existing district entry:', error);
                    // On error, clear selected articles and reset editing
                    setFormData({
                      ...formData,
                      districtId: districtId,
                      districtName: district?.name,
                      selectedArticles: [],
                    });
                    setEditingRecordId(null);
                  }
                } else {
                  // District cleared, reset form
                  setFormData({
                    ...formData,
                    districtId: '',
                    districtName: '',
                    selectedArticles: [],
                  });
                  setEditingRecordId(null);
                }
              }
            }}
            disabled={loadingDistricts}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <option value="">{loadingDistricts ? 'Loading districts...' : 'Select District'}</option>
            {districts.map((district) => (
              <option key={district.id} value={district.id}>
                {district.name}
              </option>
            ))}
          </select>
          {errors.districtId && (
            <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.districtId}</p>
          )}
        </div>

        {selectedDistrict && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                President
              </label>
              <p className="text-gray-900 dark:text-white">{selectedDistrict.presidentName}</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Mobile Number
              </label>
              <p className="text-gray-900 dark:text-white">{selectedDistrict.mobileNumber}</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Allotted Fund
              </label>
              <p className="text-gray-900 dark:text-white">
                {CURRENCY_SYMBOL}{selectedDistrict.allottedBudget.toLocaleString('en-IN')}
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Remaining Fund
              </label>
              <p className={`font-semibold ${remainingFund < 0
                  ? 'text-red-600 dark:text-red-400'
                  : 'text-green-600 dark:text-green-400'
                }`}>
                {loadingExistingEntries ? (
                  <span className="text-sm">Calculating...</span>
                ) : (
                  `${CURRENCY_SYMBOL}${remainingFund.toLocaleString('en-IN')}`
                )}
              </p>
              {remainingFund < 0 && (
                <p className="text-xs text-red-600 dark:text-red-400 mt-1">
                  Warning: Exceeds allotted budget
                </p>
              )}
            </div>
          </div>
        )}

        <MultiSelectArticles
          articles={articles}
          selectedArticles={formData.selectedArticles || []}
          onArticlesChange={(selected) => {
            setFormData({ ...formData, selectedArticles: selected });
          }}
          label="Select Articles"
          required
          districtId={formData.districtId}
        />
        {errors.selectedArticles && (
          <p className="text-sm text-red-600 dark:text-red-400">{errors.selectedArticles}</p>
        )}

        {/* Duplicate Articles Summary */}
        {(() => {
          const duplicateArticles = getDuplicateArticles(formData.selectedArticles || []);
          return duplicateArticles.length > 0 && (
            <div className="p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
              <div className="flex items-start gap-2">
                <Info className="w-4 h-4 text-blue-600 dark:text-blue-400 mt-0.5 flex-shrink-0" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-blue-900 dark:text-blue-100 mb-1">
                    Multiple entry article:
                  </p>
                  <ul className="text-xs text-blue-800 dark:text-blue-300 list-disc list-inside">
                    {duplicateArticles.map((dup, idx) => (
                      <li key={idx}>
                        {dup.name} (added {dup.count} times) : Advisable to Split as Single Quantity and add Comments for such entries
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          );
        })()}

        <div className="flex items-end gap-4">
          <div className="w-full max-w-xs">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Total Accrued
            </label>
            <div className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white font-semibold text-base">
              {CURRENCY_SYMBOL}{calculateTotalAccrued().toLocaleString('en-IN')}
            </div>
          </div>
        </div>

        {/* Save/Cancel Buttons */}
        <div className="flex justify-end gap-3 pt-6 border-t border-gray-200 dark:border-gray-700 mt-6">
          <button
            onClick={handleCancel}
            disabled={isSaving}
            className="flex items-center gap-2 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <X className="w-4 h-4" />
            <span>Cancel</span>
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Saving...</span>
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                <span>Save</span>
              </>
            )}
          </button>
        </div>
      </div>
    );
  };

  // Public form
  const renderPublicForm = () => {
    const selectedArticle = formData.articleId ? getArticleById(formData.articleId) : null;
    const costPerUnit = formData.costPerUnit ?? selectedArticle?.costPerUnit ?? 0;
    const quantity = formData.quantity || 1;
    const totalValue = formData.totalValue ?? costPerUnit * quantity;

    return (
      <div className="space-y-4">
          {editingRecordId && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Application Number
              </label>
              <input
                type="text"
                value={
                  formData.applicationNumber || ''
                  // : generateApplicationNumber('public')
                }
                readOnly
                className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white cursor-not-allowed"
              />
            </div>
          )}

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Aadhar Number <span className="text-red-500">*</span>
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              maxLength={12}
              value={formData.aadharNumber || ''}
              onChange={(e) => {
                const value = e.target.value.replace(/\D/g, '');
                setFormData({ ...formData, aadharNumber: value });
                setIsAadharVerified(false); // Reset verification when Aadhar changes
                setMatchedHistoryRecords([]); // Clear matched records when Aadhar changes
              }}
              className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              placeholder="Enter 12-digit Aadhar number"
            />
            <button
              type="button"
              onClick={handleVerifyAadhar}
              disabled={!formData.aadharNumber || formData.aadharNumber.length !== 12 || isVerifyingAadhar}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap flex items-center gap-2"
            >
              {isVerifyingAadhar ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Verifying...</span>
                </>
              ) : (
                <span>Verify</span>
              )}
            </button>
          </div>
          {errors.aadharNumber && (
            <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.aadharNumber}</p>
          )}
          {isAadharVerified && (
            <div className="mt-2">
              {matchedHistoryRecords.length > 0 ? (
                <div className="p-4 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg">
                  <p className="text-sm font-medium text-yellow-900 dark:text-yellow-100 mb-3">
                    ⚠️ Aadhar number verified - Found {matchedHistoryRecords.length} previous record{matchedHistoryRecords.length > 1 ? 's' : ''}:
                  </p>
                  <div className="space-y-3">
                    {matchedHistoryRecords.map((record, index) => (
                      <div key={index} className="p-3 bg-white dark:bg-gray-800 rounded border border-yellow-200 dark:border-yellow-700">
                        <p className="text-xs font-semibold text-yellow-800 dark:text-yellow-200 mb-2">
                          Record {index + 1}:
                        </p>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm text-gray-700 dark:text-gray-300">
                          <div>
                            <span className="font-medium">Name:</span> {record.name || 'N/A'}
                          </div>
                          <div>
                            <span className="font-medium">Year:</span> {record.year || 'N/A'}
                          </div>
                          <div>
                            <span className="font-medium">Article:</span> {record.article_name || 'N/A'}
                          </div>
                          {record.application_number && (
                            <div>
                              <span className="font-medium">App No:</span> {record.application_number}
                            </div>
                          )}
                          <div>
                            <span className="font-medium">Handicapped:</span> {record.is_handicapped ? 'Yes' : 'No'}
                          </div>
                          <div className="md:col-span-2">
                            <span className="font-medium">Comments:</span> {record.comments || record.comment || 'N/A'}
                          </div>
                          {record.address && (
                            <div className="md:col-span-2">
                              <span className="font-medium">Address:</span> {record.address}
                            </div>
                          )}
                          {record.mobile && (
                            <div>
                              <span className="font-medium">Mobile:</span> {record.mobile}
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="text-sm text-green-600 dark:text-green-400">
                  ✓ Aadhar number verified - No previous records found
                </p>
              )}
            </div>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Name <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={formData.name || ''}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
          />
          {errors.name && (
            <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.name}</p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Handicapped
          </label>
          <div className="flex gap-4">
            <label className="flex items-center">
              <input
                type="radio"
                name="handicapped"
                checked={formData.handicapped === true}
                onChange={() => setFormData({ ...formData, handicapped: true })}
                className="mr-2"
              />
              <span className="text-gray-700 dark:text-gray-300">Yes</span>
            </label>
            <label className="flex items-center">
              <input
                type="radio"
                name="handicapped"
                checked={formData.handicapped === false}
                onChange={() => setFormData({ ...formData, handicapped: false })}
                className="mr-2"
              />
              <span className="text-gray-700 dark:text-gray-300">No</span>
            </label>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Gender <span className="text-red-500">*</span>
          </label>
          <div className="flex gap-4">
            <label className="flex items-center">
              <input
                type="radio"
                name="gender"
                value="Male"
                checked={formData.gender === 'Male'}
                onChange={(e) => setFormData({ ...formData, gender: e.target.value as 'Male' | 'Female' | 'Transgender', femaleStatus: undefined })}
                className="mr-2"
              />
              <span className="text-gray-700 dark:text-gray-300">Male</span>
            </label>
            <label className="flex items-center">
              <input
                type="radio"
                name="gender"
                value="Female"
                checked={formData.gender === 'Female'}
                onChange={(e) => setFormData({ ...formData, gender: e.target.value as 'Male' | 'Female' | 'Transgender', femaleStatus: undefined })}
                className="mr-2"
              />
              <span className="text-gray-700 dark:text-gray-300">Female</span>
            </label>
            <label className="flex items-center">
              <input
                type="radio"
                name="gender"
                value="Transgender"
                checked={formData.gender === 'Transgender'}
                onChange={(e) => setFormData({ ...formData, gender: e.target.value as 'Male' | 'Female' | 'Transgender', femaleStatus: undefined })}
                className="mr-2"
              />
              <span className="text-gray-700 dark:text-gray-300">Transgender</span>
            </label>
          </div>
          {errors.gender && (
            <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.gender}</p>
          )}
        </div>

        {formData.gender === 'Female' && (
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Female Status
            </label>
            <div className="flex flex-wrap gap-4">
              <label className="flex items-center">
                <input
                  type="radio"
                  name="femaleStatus"
                  value="Single Mother"
                  checked={formData.femaleStatus === 'Single Mother'}
                  onChange={(e) => setFormData({ ...formData, femaleStatus: e.target.value as 'Single Mother' | 'Widow' | 'Married' | 'Unmarried' })}
                  className="mr-2"
                />
                <span className="text-gray-700 dark:text-gray-300">Single Mother</span>
              </label>
              <label className="flex items-center">
                <input
                  type="radio"
                  name="femaleStatus"
                  value="Widow"
                  checked={formData.femaleStatus === 'Widow'}
                  onChange={(e) => setFormData({ ...formData, femaleStatus: e.target.value as 'Single Mother' | 'Widow' | 'Married' | 'Unmarried' })}
                  className="mr-2"
                />
                <span className="text-gray-700 dark:text-gray-300">Widow</span>
              </label>
              <label className="flex items-center">
                <input
                  type="radio"
                  name="femaleStatus"
                  value="Married"
                  checked={formData.femaleStatus === 'Married'}
                  onChange={(e) => setFormData({ ...formData, femaleStatus: e.target.value as 'Single Mother' | 'Widow' | 'Married' | 'Unmarried' })}
                  className="mr-2"
                />
                <span className="text-gray-700 dark:text-gray-300">Married</span>
              </label>
              <label className="flex items-center">
                <input
                  type="radio"
                  name="femaleStatus"
                  value="Unmarried"
                  checked={formData.femaleStatus === 'Unmarried'}
                  onChange={(e) => setFormData({ ...formData, femaleStatus: e.target.value as 'Single Mother' | 'Widow' | 'Married' | 'Unmarried' })}
                  className="mr-2"
                />
                <span className="text-gray-700 dark:text-gray-300">Unmarried</span>
              </label>
            </div>
          </div>
        )}

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Address
          </label>
          <textarea
            value={formData.address || ''}
            onChange={(e) => setFormData({ ...formData, address: e.target.value })}
            rows={3}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white resize-none"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Mobile Number <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={formData.mobile || ''}
            onChange={(e) => {
              // Allow digits and ampersand only
              let value = e.target.value.replace(/[^\d& ]/g, '');
              value = value.replace(/&+/g, '&');
              setFormData({ ...formData, mobile: value });
            }}
            onBlur={(e) => {
              let value = e.target.value.replace(/[^\d& ]/g, '');
              value = value.replace(/&+/g, '&');
              value = value.replace(/\s+/g, ' ').trim();
              if (value.startsWith('&')) {
                value = value.substring(1);
              }
              const normalized = value
                .split('&')
                .map((num) => num.trim())
                .filter((num) => num.length > 0)
                .join(' & ');
              setFormData({ ...formData, mobile: normalized });
            }}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            placeholder="Enter mobile number(s) separated by & (e.g., 1234567890 & 9876543210)"
          />
          {errors.mobile && (
            <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.mobile}</p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Select Article <span className="text-red-500">*</span>
          </label>
          <select
            value={formData.articleId || ''}
            onChange={(e) => {
              const article = getArticleById(e.target.value);
              setFormData({
                ...formData,
                articleId: e.target.value,
                costPerUnit: article?.costPerUnit || 0,
              });
            }}
            disabled={loadingArticles}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <option value="">{loadingArticles ? 'Loading articles...' : 'Select Article'}</option>
            {articles.map((article) => (
              <option key={article.id} value={article.id}>
                {article.name} ({CURRENCY_SYMBOL}{article.costPerUnit.toLocaleString('en-IN')})
              </option>
            ))}
          </select>
          {errors.articleId && (
            <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.articleId}</p>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Cost Per Unit
            </label>
            <input
              type="number"
              value={costPerUnit === 0 ? '' : costPerUnit}
              onChange={(e) => {
                const inputValue = e.target.value;
                // Allow empty string for clearing
                if (inputValue === '') {
                  setFormData({
                    ...formData,
                    costPerUnit: 0,
                    totalValue: 0,
                  });
                  return;
                }
                // Remove leading zeros by parsing - parseFloat naturally removes leading zeros
                const value = inputValue === '0' ? 0 : parseFloat(inputValue) || 0;
                const newQuantity = formData.quantity || 1;
                setFormData({
                  ...formData,
                  costPerUnit: value,
                  totalValue: value * newQuantity,
                });
              }}
              disabled={false}
              className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white disabled:bg-gray-50 dark:disabled:bg-gray-800 disabled:cursor-not-allowed"
            />
            {errors.costPerUnit && (
              <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.costPerUnit}</p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Quantity <span className="text-red-500">*</span>
            </label>
            <input
              type="number"
              min="1"
              value={quantity}
              onChange={(e) => {
                const value = parseInt(e.target.value, 10) || 0;
                const currentCostPerUnit = formData.costPerUnit ?? selectedArticle?.costPerUnit ?? 0;
                setFormData({
                  ...formData,
                  quantity: value,
                  totalValue: currentCostPerUnit * value,
                });
              }}
              className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
            {errors.quantity && (
              <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.quantity}</p>
            )}
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Total Value
          </label>
          <div className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white font-medium">
            {CURRENCY_SYMBOL}{totalValue.toLocaleString('en-IN')}
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Comments
          </label>
          <textarea
            value={formData.comments || ''}
            onChange={(e) => setFormData({ ...formData, comments: e.target.value })}
            rows={3}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white resize-none"
          />
        </div>

        <div className="flex items-end gap-4">
          <div className="w-full max-w-xs">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Total Accrued
            </label>
            <div className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white font-semibold text-base">
              {CURRENCY_SYMBOL}{totalValue.toLocaleString('en-IN')}
            </div>
          </div>
        </div>

        {/* Save/Cancel Buttons */}
        <div className="flex justify-end gap-3 pt-6 border-t border-gray-200 dark:border-gray-700 mt-6">
          <button
            onClick={handleCancel}
            disabled={isSaving}
            className="flex items-center gap-2 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <X className="w-4 h-4" />
            <span>Cancel</span>
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Saving...</span>
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                <span>Save</span>
              </>
            )}
          </button>
        </div>
      </div>
    );
  };

  // Institutions form
  const renderInstitutionsForm = () => {
    return (
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Name <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={formData.institutionName || ''}
            onChange={(e) => setFormData({ ...formData, institutionName: e.target.value })}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
          />
          {errors.institutionName && (
            <p className="mt-1 text-sm text-red-600 dark:text-red-400">
              {errors.institutionName}
            </p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Institution Type <span className="text-red-500">*</span>
          </label>
          <select
            value={formData.institutionType || ''}
            onChange={(e) =>
              setFormData({
                ...formData,
                institutionType: e.target.value as 'institutions' | 'others',
              })
            }
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
          >
            <option value="">Select Type</option>
            {institutionTypes.map((type) => (
              <option key={type} value={type}>
                {type.charAt(0).toUpperCase() + type.slice(1)}
              </option>
            ))}
          </select>
          {errors.institutionType && (
            <p className="mt-1 text-sm text-red-600 dark:text-red-400">
              {errors.institutionType}
            </p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Address
          </label>
          <textarea
            value={formData.address || ''}
            onChange={(e) => setFormData({ ...formData, address: e.target.value })}
            rows={3}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white resize-none"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Mobile Number
          </label>
          <input
            type="text"
            value={formData.mobile || ''}
            onChange={(e) => {
              const value = e.target.value.replace(/\D/g, '');
              setFormData({ ...formData, mobile: value });
            }}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            placeholder="Enter mobile number"
          />
        </div>

        {loadingArticles ? (
          <div className="text-sm text-gray-500 dark:text-gray-400">Loading articles...</div>
        ) : (
          <>
            <MultiSelectArticles
              articles={articles}
              selectedArticles={formData.selectedArticles || []}
              onArticlesChange={(selected) => {
                setFormData({ ...formData, selectedArticles: selected });
              }}
              label="Select Articles"
              required
            />
            {errors.selectedArticles && (
              <p className="text-sm text-red-600 dark:text-red-400">{errors.selectedArticles}</p>
            )}
          </>
        )}

        {/* Duplicate Articles Summary */}
        {(() => {
          const duplicateArticles = getDuplicateArticles(formData.selectedArticles || []);
          return duplicateArticles.length > 0 && (
            <div className="p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
              <div className="flex items-start gap-2">
                <Info className="w-4 h-4 text-blue-600 dark:text-blue-400 mt-0.5 flex-shrink-0" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-blue-900 dark:text-blue-100 mb-1">
                    Multiple entry article:
                  </p>
                  <ul className="text-xs text-blue-800 dark:text-blue-300 list-disc list-inside">
                    {duplicateArticles.map((dup, idx) => (
                      <li key={idx}>
                        {dup.name} (added {dup.count} times)
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          );
        })()}

        <div className="flex items-end gap-4">
          <div className="w-full max-w-xs">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Total Accrued
            </label>
            <div className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white font-semibold text-base">
              {CURRENCY_SYMBOL}{calculateTotalAccrued().toLocaleString('en-IN')}
            </div>
          </div>
        </div>

        {/* Save/Cancel Buttons */}
        <div className="flex justify-end gap-3 pt-6 border-t border-gray-200 dark:border-gray-700 mt-6">
          <button
            onClick={handleCancel}
            disabled={isSaving}
            className="flex items-center gap-2 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <X className="w-4 h-4" />
            <span>Cancel</span>
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Saving...</span>
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                <span>Save</span>
              </>
            )}
          </button>
        </div>
      </div>
    );
  };

  // Render table
  const renderTable = () => {
    if (loadingRecords) {
      return (
        <div className="text-center py-12 text-gray-500 dark:text-gray-400">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 dark:border-blue-400 mb-2"></div>
          <p>Loading records...</p>
        </div>
      );
    }

    const filteredAndSortedRecords = getFilteredAndSortedRecords();

    if (filteredAndSortedRecords.length === 0) {
      const hasFilters = searchQuery.trim() || dateFilter.start || dateFilter.end;
      return (
        <div className="text-center py-12 text-gray-500 dark:text-gray-400">
          {hasFilters ? 'No records found matching your filters' : `No records found for ${beneficiaryTypeFilter} type`}
        </div>
      );
    }

    return (
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              {beneficiaryTypeFilter === 'district' && (
                <>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                    onClick={() => handleSort('applicationNumber')}
                  >
                    <div className="flex items-center gap-1">
                      App Number
                      <span className={`text-xs ${sortColumn === 'applicationNumber' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('applicationNumber')}
                      </span>
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                    onClick={() => handleSort('districtName')}
                  >
                    <div className="flex items-center gap-1">
                      District Name
                      <span className={`text-xs ${sortColumn === 'districtName' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('districtName')}
                      </span>
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                    onClick={() => handleSort('articlesCount')}
                  >
                    <div className="flex items-center gap-1">
                      Articles
                      <span className={`text-xs ${sortColumn === 'articlesCount' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('articlesCount')}
                      </span>
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                    onClick={() => handleSort('totalAccrued')}
                  >
                    <div className="flex items-center gap-1">
                      Total Accrued
                      <span className={`text-xs ${sortColumn === 'totalAccrued' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('totalAccrued')}
                      </span>
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                    onClick={() => handleSort('remainingFund')}
                  >
                    <div className="flex items-center gap-1">
                      Remaining Fund
                      <span className={`text-xs ${sortColumn === 'remainingFund' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('remainingFund')}
                      </span>
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                    onClick={() => handleSort('createdAt')}
                  >
                    <div className="flex items-center gap-1">
                      Created At
                      <span className={`text-xs ${sortColumn === 'createdAt' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('createdAt')}
                      </span>
                    </div>
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700">
                    Actions
                  </th>
                </>
              )}
              {beneficiaryTypeFilter === 'public' && (
                <>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                    onClick={() => handleSort('applicationNumber')}
                  >
                    <div className="flex items-center gap-1">
                      App Number
                      <span className={`text-xs ${sortColumn === 'applicationNumber' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('applicationNumber')}
                      </span>
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                    onClick={() => handleSort('name')}
                  >
                    <div className="flex items-center gap-1">
                      Name
                      <span className={`text-xs ${sortColumn === 'name' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('name')}
                      </span>
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                    onClick={() => handleSort('gender')}
                  >
                    <div className="flex items-center gap-1">
                      Gender
                      <span className={`text-xs ${sortColumn === 'gender' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('gender')}
                      </span>
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                    onClick={() => handleSort('aadharNumber')}
                  >
                    <div className="flex items-center gap-1">
                      Aadhar
                      <span className={`text-xs ${sortColumn === 'aadharNumber' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('aadharNumber')}
                      </span>
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                    onClick={() => handleSort('article')}
                  >
                    <div className="flex items-center gap-1">
                      Article
                      <span className={`text-xs ${sortColumn === 'article' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('article')}
                      </span>
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                    onClick={() => handleSort('totalValue')}
                  >
                    <div className="flex items-center gap-1">
                      Total Value
                      <span className={`text-xs ${sortColumn === 'totalValue' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('totalValue')}
                      </span>
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                    onClick={() => handleSort('handicapped')}
                  >
                    <div className="flex items-center gap-1">
                      Handicapped
                      <span className={`text-xs ${sortColumn === 'handicapped' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('handicapped')}
                      </span>
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                    onClick={() => handleSort('createdAt')}
                  >
                    <div className="flex items-center gap-1">
                      Created At
                      <span className={`text-xs ${sortColumn === 'createdAt' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('createdAt')}
                      </span>
                    </div>
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700">
                    Actions
                  </th>
                </>
              )}
              {beneficiaryTypeFilter === 'institutions' && (
                <>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                    onClick={() => handleSort('applicationNumber')}
                  >
                    <div className="flex items-center gap-1">
                      App Number
                      <span className={`text-xs ${sortColumn === 'applicationNumber' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('applicationNumber')}
                      </span>
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                    onClick={() => handleSort('name')}
                  >
                    <div className="flex items-center gap-1">
                      Name
                      <span className={`text-xs ${sortColumn === 'name' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('name')}
                      </span>
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                    onClick={() => handleSort('institutionType')}
                  >
                    <div className="flex items-center gap-1">
                      Type
                      <span className={`text-xs ${sortColumn === 'institutionType' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('institutionType')}
                      </span>
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                    onClick={() => handleSort('articlesCount')}
                  >
                    <div className="flex items-center gap-1">
                      Articles
                      <span className={`text-xs ${sortColumn === 'articlesCount' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('articlesCount')}
                      </span>
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                    onClick={() => handleSort('totalAccrued')}
                  >
                    <div className="flex items-center gap-1">
                      Total Accrued
                      <span className={`text-xs ${sortColumn === 'totalAccrued' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('totalAccrued')}
                      </span>
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                    onClick={() => handleSort('createdAt')}
                  >
                    <div className="flex items-center gap-1">
                      Created At
                      <span className={`text-xs ${sortColumn === 'createdAt' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('createdAt')}
                      </span>
                    </div>
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700">
                    Actions
                  </th>
                </>
              )}
            </tr>
          </thead>
          <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-700">
            {filteredAndSortedRecords.map((record) => {
              const isExpanded = expandedRows.has(record.id);
              const canExpandDistrict = (beneficiaryTypeFilter === 'district' || beneficiaryTypeFilter === 'institutions') &&
                record.selectedArticles && record.selectedArticles.length > 0;
              const canExpandPublic = beneficiaryTypeFilter === 'public' && (
                record.address || record.mobile || record.quantity || record.comments || 
                (record.gender === 'Female' && record.femaleStatus)
              );
              const canExpand = canExpandDistrict || canExpandPublic;

              return (
                <React.Fragment key={record.id}>
                  <tr
                    className={`hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors ${canExpand ? 'cursor-pointer' : ''}`}
                    onClick={() => canExpand && toggleRowExpansion(record.id)}
                  >
                    {beneficiaryTypeFilter === 'district' && (
                      <>
                        <td className="px-4 py-3 text-sm text-gray-900 dark:text-white">
                          {record.applicationNumber}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-900 dark:text-white">
                          {record.districtName}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                          {new Set((record.selectedArticles || []).map(article => article.articleId)).size} item(s), {record.selectedArticles?.reduce((sum, article) => sum + (article.quantity || 0), 0) || 0} quantity
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-900 dark:text-white font-medium">
                          {CURRENCY_SYMBOL}{(record.totalAccrued || 0).toLocaleString('en-IN')}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-900 dark:text-white font-medium">
                          {(() => {
                            // Calculate remaining fund for this district
                            const district = record.districtId ? getDistrictById(record.districtId) : null;
                            if (!district) return '-';

                            // Get all entries for this district to calculate total used
                            const districtRecords = records.filter(
                              r => r.beneficiaryType === 'district' && r.districtId === record.districtId
                            );
                            const totalUsed = districtRecords.reduce(
                              (sum, r) => sum + (r.totalAccrued || 0),
                              0
                            );
                            const remaining = district.allottedBudget - totalUsed;

                            return (
                              <span className={remaining < 0
                                ? 'text-red-600 dark:text-red-400'
                                : 'text-green-600 dark:text-green-400'}>
                                {CURRENCY_SYMBOL}{remaining.toLocaleString('en-IN')}
                              </span>
                            );
                          })()}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                          {record.createdAt ? new Date(record.createdAt).toLocaleDateString('en-IN', {
                            year: 'numeric',
                            month: '2-digit',
                            day: '2-digit'
                          }) : '-'}
                        </td>
                        <td className="px-4 py-3 text-sm">
                          <div className="flex items-center gap-2">
                            {canUpdate() && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleRowClick(record);
                                }}
                                className="p-1.5 text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/30 rounded transition-colors"
                                aria-label="Edit"
                              >
                                <Pencil className="w-4 h-4" />
                              </button>
                            )}
                            {canDelete() && (
                              <button
                                onClick={(e) => handleDelete(e, record.id)}
                                className="p-1.5 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/30 rounded transition-colors"
                                aria-label="Delete"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            )}
                          </div>
                        </td>
                      </>
                    )}
                    {beneficiaryTypeFilter === 'public' && (
                      <>
                        <td className="px-4 py-3 text-sm text-gray-900 dark:text-white">
                          <div className="flex items-center gap-2">
                            {canExpandPublic && (
                              <span className="text-gray-400">
                                {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                              </span>
                            )}
                            {record.applicationNumber}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-900 dark:text-white">
                          {record.name}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                          {record.gender || '-'}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                          {record.aadharNumber}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                          {getArticleById(record.articleId || '')?.name || '-'}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-900 dark:text-white font-medium">
                          {CURRENCY_SYMBOL}{(record.totalValue || 0).toLocaleString('en-IN')}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                          {record.handicapped ? 'Yes' : 'No'}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                          {record.createdAt ? new Date(record.createdAt).toLocaleDateString('en-IN', {
                            year: 'numeric',
                            month: '2-digit',
                            day: '2-digit'
                          }) : '-'}
                        </td>
                        <td className="px-4 py-3 text-sm">
                          <div className="flex items-center gap-2">
                            {canUpdate() && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleRowClick(record);
                                }}
                                className="p-1.5 text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/30 rounded transition-colors"
                                aria-label="Edit"
                              >
                                <Pencil className="w-4 h-4" />
                              </button>
                            )}
                            {canDelete() && (
                              <button
                                onClick={(e) => handleDelete(e, record.id)}
                                className="p-1.5 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/30 rounded transition-colors"
                                aria-label="Delete"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            )}
                          </div>
                        </td>
                      </>
                    )}
                    {beneficiaryTypeFilter === 'institutions' && (
                      <>
                        <td className="px-4 py-3 text-sm text-gray-900 dark:text-white">
                          {record.applicationNumber}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-900 dark:text-white">
                          {record.institutionName}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400 capitalize">
                          {record.institutionType}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                          {new Set((record.selectedArticles || []).map(article => article.articleId)).size} item(s), {record.selectedArticles?.reduce((sum, article) => sum + (article.quantity || 0), 0) || 0} quantity
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-900 dark:text-white font-medium">
                          {CURRENCY_SYMBOL}{(record.totalAccrued || 0).toLocaleString('en-IN')}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                          {record.createdAt ? new Date(record.createdAt).toLocaleDateString('en-IN', {
                            year: 'numeric',
                            month: '2-digit',
                            day: '2-digit'
                          }) : '-'}
                        </td>
                        <td className="px-4 py-3 text-sm" onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center gap-2">
                            {canUpdate() && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleRowClick(record);
                                }}
                                className="p-1.5 text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/30 rounded transition-colors"
                                aria-label="Edit"
                              >
                                <Pencil className="w-4 h-4" />
                              </button>
                            )}
                            {canDelete() && (
                              <button
                                onClick={(e) => handleDelete(e, record.id)}
                                className="p-1.5 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/30 rounded transition-colors"
                                aria-label="Delete"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            )}
                          </div>
                        </td>
                      </>
                    )}
                  </tr>
                  {/* Expanded row for district, institutions, and public */}
                  {isExpanded && canExpand && (
                    <tr>
                      <td
                        colSpan={
                          beneficiaryTypeFilter === 'district' ? 6 :
                          beneficiaryTypeFilter === 'public' ? 8 :
                          7
                        }
                        className="px-4 py-4 bg-gray-50 dark:bg-gray-800"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {beneficiaryTypeFilter === 'public' ? (
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-x-6 gap-y-3">
                            {record.address && (
                              <div className="md:col-span-2">
                                <span className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">Address:</span>
                                <p className="text-sm text-gray-900 dark:text-white">{record.address}</p>
                              </div>
                            )}
                            {record.mobile && (
                              <div>
                                <span className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">Mobile:</span>
                                <p className="text-sm text-gray-900 dark:text-white">{record.mobile}</p>
                              </div>
                            )}
                            {record.quantity && (
                              <div>
                                <span className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">Quantity:</span>
                                <p className="text-sm text-gray-900 dark:text-white">{record.quantity}</p>
                              </div>
                            )}
                            {record.gender === 'Female' && record.femaleStatus && (
                              <div>
                                <span className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">Female Status:</span>
                                <p className="text-sm text-gray-900 dark:text-white">{record.femaleStatus}</p>
                              </div>
                            )}
                            {record.comments && (
                              <div className="md:col-span-3">
                                <span className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">Comments:</span>
                                <p className="text-sm text-gray-900 dark:text-white">{record.comments || '-'}</p>
                              </div>
                            )}
                          </div>
                        ) : (
                          <div className="space-y-2">
                            <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">
                              Articles
                            </h4>
                            {record.selectedArticles && record.selectedArticles.length > 0 ? (
                              <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                  <thead>
                                    <tr className="border-b border-gray-200 dark:border-gray-700">
                                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-600 dark:text-gray-400">Article Name</th>
                                      <th className="px-3 py-2 text-center text-xs font-medium text-gray-600 dark:text-gray-400">Quantity</th>
                                      <th className="px-3 py-2 text-right text-xs font-medium text-gray-600 dark:text-gray-400">Cost/Unit</th>
                                      <th className="px-3 py-2 text-right text-xs font-medium text-gray-600 dark:text-gray-400">Total Value</th>
                                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-600 dark:text-gray-400">Comments</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {[...record.selectedArticles].sort((a, b) => a.articleName.localeCompare(b.articleName)).map((article, idx) => (
                                      <tr key={idx} className="border-b border-gray-200 dark:border-gray-700">
                                        <td className="px-3 py-2 text-gray-900 dark:text-white">{article.articleName}</td>
                                        <td className="px-3 py-2 text-center text-gray-900 dark:text-white">{article.quantity}</td>
                                        <td className="px-3 py-2 text-right text-gray-900 dark:text-white">{CURRENCY_SYMBOL}{article.costPerUnit.toLocaleString('en-IN')}</td>
                                        <td className="px-3 py-2 text-right text-gray-900 dark:text-white font-medium">{CURRENCY_SYMBOL}{article.totalValue.toLocaleString('en-IN')}</td>
                                        <td className="px-3 py-2 text-gray-600 dark:text-gray-400">{article.comments || '-'}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            ) : (
                              <p className="text-sm text-gray-500 dark:text-gray-400">No articles found.</p>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  };

  return (
    <div className="p-4 sm:p-6 relative">
      {/* Full-screen loading overlay for deletion */}
      {isDeleting && (
        <div className="fixed inset-0 bg-black/50 dark:bg-black/70 z-50 flex items-center justify-center">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 flex flex-col items-center gap-4 shadow-xl">
            <Loader2 className="w-8 h-8 animate-spin text-blue-600 dark:text-blue-400" />
            <p className="text-sm font-medium text-gray-900 dark:text-white">Deleting record...</p>
          </div>
        </div>
      )}
      
      {/* Sticky Header */}
      <div className="sticky top-0 z-20 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 pb-4 mb-4 px-1 shadow-sm">
        <div className="flex flex-col gap-3 sm:gap-4">
          <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3 lg:gap-4">
            <div className="flex items-center gap-2 sm:gap-3 flex-1 min-w-0">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300 whitespace-nowrap flex-shrink-0">
                Beneficiary Type:
              </label>
              <select
                value={beneficiaryTypeFilter}
                onChange={(e) => {
                  setBeneficiaryTypeFilter(e.target.value as BeneficiaryType);
                  setIsFormMode(false);
                  resetForm();
                }}
                disabled={isFormMode}
                className="flex-1 sm:flex-initial min-w-[140px] max-w-[200px] px-3 sm:px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed text-sm"
              >
                <option value="district">District</option>
                <option value="public">Public</option>
                <option value="institutions">Institutions & Others</option>
              </select>
            </div>

            <div className="flex flex-wrap items-center gap-2 sm:gap-3 flex-shrink-0">
              {!isFormMode && (
                <>
                  {/* Date Filter - moved to right side */}
                  <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                    <label className="text-xs sm:text-sm text-gray-700 dark:text-gray-300 whitespace-nowrap flex-shrink-0">From:</label>
                    <input
                      type="date"
                      value={dateFilter.start || ''}
                      onChange={(e) => setDateFilter({ ...dateFilter, start: e.target.value || null })}
                      className="min-w-0 flex-1 sm:flex-initial sm:w-32 px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-xs sm:text-sm"
                    />
                    <label className="text-xs sm:text-sm text-gray-700 dark:text-gray-300 whitespace-nowrap flex-shrink-0">To:</label>
                    <input
                      type="date"
                      value={dateFilter.end || ''}
                      onChange={(e) => setDateFilter({ ...dateFilter, end: e.target.value || null })}
                      min={dateFilter.start || undefined}
                      className="min-w-0 flex-1 sm:flex-initial sm:w-32 px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-xs sm:text-sm"
                    />
                    {(dateFilter.start || dateFilter.end) && (
                      <button
                        onClick={() => setDateFilter({ start: null, end: null })}
                        className="px-2 py-1.5 text-xs text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white flex-shrink-0"
                        aria-label="Clear date filter"
                        title="Clear date filter"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                  
                  {canExport() && (
                    <button
                      onClick={handleExportClick}
                      className="flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors whitespace-nowrap flex-shrink-0 text-sm"
                    >
                      <Download className="w-4 h-4" />
                      <span className="hidden sm:inline">Export</span>
                    </button>
                  )}
                  <button
                    onClick={loadRecords}
                    disabled={loadingRecords}
                    className="flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0 text-sm"
                  >
                    <RefreshCw className={`w-4 h-4 ${loadingRecords ? 'animate-spin' : ''}`} />
                    <span className="hidden sm:inline">Refresh</span>
                  </button>
                  {canCreate() && (
                    <button
                      onClick={handleAdd}
                      className="flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors whitespace-nowrap w-full sm:w-auto justify-center flex-shrink-0 text-sm"
                    >
                      <Plus className="w-4 h-4" />
                      <span>Add</span>
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
          
          {/* Search Bar for all beneficiary types */}
          {!isFormMode && (
            <div className="flex items-center gap-2">
              <div className="relative flex-1 max-w-md">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder={
                    beneficiaryTypeFilter === 'district'
                      ? 'Search by application number, district name, or article...'
                      : beneficiaryTypeFilter === 'public'
                      ? 'Search by application number, name, Aadhar, mobile, or article...'
                      : 'Search by application number, institution name, or article...'
                  }
                  className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                />
              </div>
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="px-3 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
                  aria-label="Clear search"
                >
                  Clear
                </button>
              )}
              <span className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap ml-auto">
                Total: {getFilteredAndSortedRecords().length}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      {isFormMode ? (
        <div className={`bg-white dark:bg-gray-800 rounded-lg shadow p-4 border border-gray-200 dark:border-gray-700 ${isSaving ? 'pointer-events-none opacity-50' : ''}`}>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            {editingRecordId ? 'Edit' : 'Add New'} {beneficiaryTypeFilter.charAt(0).toUpperCase() + beneficiaryTypeFilter.slice(1)} Entry
          </h2>

          {formData.beneficiaryType === 'district' && renderDistrictForm()}
          {formData.beneficiaryType === 'public' && renderPublicForm()}
          {formData.beneficiaryType === 'institutions' && renderInstitutionsForm()}
        </div>
      ) : (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700 overflow-hidden">
          {renderTable()}
        </div>
      )}

      {/* Export Modal */}
      {showExportModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full">
            <div className="flex justify-between items-center p-6 border-b border-gray-200 dark:border-gray-700">
              <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                Export Master Entries
              </h2>
              <button
                onClick={() => {
                  setShowExportModal(false);
                  setExportType('all');
                }}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-4">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                Select beneficiary type to export. A CSV file will be generated with consolidated fields.
              </p>

              <div className="space-y-3">
                <label className="flex items-center space-x-3 cursor-pointer">
                  <input
                    type="radio"
                    name="exportType"
                    value="all"
                    checked={exportType === 'all'}
                    onChange={(e) => setExportType(e.target.value as 'all' | 'district' | 'public' | 'institutions')}
                    className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                  />
                  <span className="text-gray-900 dark:text-white">All</span>
                </label>

                <label className="flex items-center space-x-3 cursor-pointer">
                  <input
                    type="radio"
                    name="exportType"
                    value="district"
                    checked={exportType === 'district'}
                    onChange={(e) => setExportType(e.target.value as 'all' | 'district' | 'public' | 'institutions')}
                    className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                  />
                  <span className="text-gray-900 dark:text-white">District</span>
                </label>

                <label className="flex items-center space-x-3 cursor-pointer">
                  <input
                    type="radio"
                    name="exportType"
                    value="public"
                    checked={exportType === 'public'}
                    onChange={(e) => setExportType(e.target.value as 'all' | 'district' | 'public' | 'institutions')}
                    className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                  />
                  <span className="text-gray-900 dark:text-white">Public</span>
                </label>

                <label className="flex items-center space-x-3 cursor-pointer">
                  <input
                    type="radio"
                    name="exportType"
                    value="institutions"
                    checked={exportType === 'institutions'}
                    onChange={(e) => setExportType(e.target.value as 'all' | 'district' | 'public' | 'institutions')}
                    className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                  />
                  <span className="text-gray-900 dark:text-white">Institutions & Others</span>
                </label>
              </div>

              <div className="flex justify-end space-x-3 pt-4">
                <button
                  onClick={() => {
                    setShowExportModal(false);
                    setExportType('all');
                  }}
                  className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                  disabled={exporting}
                >
                  Cancel
                </button>
                {canExport() && (
                  <button
                    onClick={handleExport}
                    disabled={exporting}
                    className="flex items-center space-x-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {exporting ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Exporting...</span>
                      </>
                    ) : (
                      <>
                        <Download className="w-4 h-4" />
                        <span>Export</span>
                      </>
                    )}
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        isOpen={confirmDialog.isOpen}
        title={confirmDialog.title}
        message={confirmDialog.message}
        type={confirmDialog.type}
        confirmText={confirmDialog.confirmText}
        secondaryText={confirmDialog.secondaryText}
        onConfirm={confirmDialog.onConfirm}
        onSecondary={confirmDialog.onSecondary}
        onCancel={() => {
          setConfirmDialog({ ...confirmDialog, isOpen: false });
          setSaving(false);
        }}
      />
    </div>
  );
};

export default MasterEntry;
