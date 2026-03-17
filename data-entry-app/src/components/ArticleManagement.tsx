import React, { useState, useEffect, useRef } from 'react';
import { Package, Plus, Edit2, Trash2, Search, Filter, X, Save, Download, Loader2, RefreshCw } from 'lucide-react';
import {
  fetchAllArticles,
  createArticle,
  updateArticle,
  deleteArticle,
} from '../services/articlesService';
import type { ArticleRecord } from '../services/articlesService';
import { exportToCSV } from '../utils/csvExport';
import { logAction } from '../services/auditLogService';
import { useAuth } from '../contexts/AuthContext';
import { useNotifications } from '../contexts/NotificationContext';
import { useRBAC } from '../contexts/RBACContext';
import { CURRENCY_SYMBOL } from '../constants/currency';
import { ConfirmDialog } from './ConfirmDialog';

const ArticleManagement: React.FC = () => {
  const { user, isAuthenticated, isRestoringSession } = useAuth();
  const { canCreate, canUpdate, canDelete, canExport } = useRBAC();
  const { showError, showSuccess, showWarning } = useNotifications();
  
  // Log when component mounts
  useEffect(() => {
    console.debug('ArticleManagement: Component mounted');
    isMountedRef.current = true;
    return () => {
      console.debug('ArticleManagement: Component unmounting');
      isMountedRef.current = false;
    };
  }, []);
  const [articles, setArticles] = useState<ArticleRecord[]>([]);
  const [filteredArticles, setFilteredArticles] = useState<ArticleRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [isFormMode, setIsFormMode] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [confirmDialog, setConfirmDialog] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    onConfirm: () => void;
    type?: 'danger' | 'warning' | 'info';
  }>({
    isOpen: false,
    title: '',
    message: '',
    onConfirm: () => {},
  });

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [itemTypeFilter, setItemTypeFilter] = useState<string>('all');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [masterCategoryFilter, setMasterCategoryFilter] = useState<string>('all');
  const [dateFilter, setDateFilter] = useState<{ start: string | null, end: string | null }>({ start: null, end: null });
  
  // Sorting
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');

  // Form state
  const [formData, setFormData] = useState({
    article_name: '',
    article_name_tk: '',
    cost_per_unit: 0,
    item_type: 'Article',
    category: '',
    master_category: '',
  });

  // Validation errors
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Save loading state
  const [isSaving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  
  // Track loading state to prevent duplicate fetches
  const isLoadingRef = useRef(false);
  const isMountedRef = useRef(true);
  
  // Category combobox state
  const [categoryDropdownOpen, setCategoryDropdownOpen] = useState(false);
  const categoryDropdownRef = useRef<HTMLDivElement>(null);
  const [masterCategoryDropdownOpen, setMasterCategoryDropdownOpen] = useState(false);
  const masterCategoryDropdownRef = useRef<HTMLDivElement>(null);

  // Load articles on component mount - only when authenticated and not restoring
  useEffect(() => {
    if (!isAuthenticated || isRestoringSession) {
      return;
    }
    
    // Prevent duplicate calls
    if (isLoadingRef.current) {
      return;
    }
    
    console.debug('ArticleManagement: Both conditions met, calling loadArticles...');
    loadArticles();
    
    return () => {
      // Reset loading flag on unmount so remount can fetch again
      isLoadingRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, isRestoringSession]); // loadArticles is stable, no need to include it

  // Apply filters when articles or filters change
  useEffect(() => {
    applyFilters();
  }, [articles, searchQuery, itemTypeFilter, categoryFilter, masterCategoryFilter, dateFilter, sortColumn, sortDirection]);

  // Close category dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (categoryDropdownRef.current && !categoryDropdownRef.current.contains(event.target as Node)) {
        setCategoryDropdownOpen(false);
      }
      if (masterCategoryDropdownRef.current && !masterCategoryDropdownRef.current.contains(event.target as Node)) {
        setMasterCategoryDropdownOpen(false);
      }
    };

    if (categoryDropdownOpen || masterCategoryDropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [categoryDropdownOpen, masterCategoryDropdownOpen]);

  const loadArticles = async (isRetry: boolean = false) => {
    // Prevent duplicate fetches
    if (isLoadingRef.current) {
      console.debug('ArticleManagement: loadArticles already in progress, skipping');
      return;
    }
    
    isLoadingRef.current = true;
    const fetchStartTime = Date.now();
    
    // Add timeout protection at component level (30 seconds)
    const timeoutId = setTimeout(() => {
      if (isLoadingRef.current) {
        isLoadingRef.current = false;
        const fetchDuration = Date.now() - fetchStartTime;
        console.error(`ArticleManagement: loadArticles timed out after ${fetchDuration}ms`);
        if (isMountedRef.current) {
          setLoading(false);
          setError('Request timed out. Please check your connection and try again.');
        }
      }
    }, 30000);
    
    try {
      if (isRetry) {
        console.debug(`ArticleManagement: Retrying loadArticles (attempt ${retryCount + 1})...`);
      } else {
        console.debug('ArticleManagement: loadArticles called, starting fetch...');
      }
      setLoading(true);
      setError(null);
      
      const data = await fetchAllArticles(false);
      clearTimeout(timeoutId);
      
      const fetchDuration = Date.now() - fetchStartTime;
      console.debug(`ArticleManagement: Articles fetched successfully in ${fetchDuration}ms, count: ${data?.length || 0}`);
      setArticles(data);
      setRetryCount(0); // Reset retry count on success
    } catch (error: any) {
      clearTimeout(timeoutId);
      const fetchDuration = Date.now() - fetchStartTime;
      console.error(`ArticleManagement: Failed to load articles after ${fetchDuration}ms:`, error);
      
      const errorMessage = error?.message || 'Failed to load articles. Please try again.';
      setError(errorMessage);
      
      // Don't show notification if it's a timeout (already handled)
      if (!errorMessage.includes('timeout')) {
        showError(errorMessage);
      }
    } finally {
      isLoadingRef.current = false;
      setLoading(false);
      const fetchDuration = Date.now() - fetchStartTime;
      console.debug(`ArticleManagement: loadArticles completed in ${fetchDuration}ms`);
    }
  };
  
  const handleRetry = () => {
    setRetryCount(prev => prev + 1);
    loadArticles(true);
  };

  const applyFilters = () => {
    let filtered = [...articles];

    // Search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (article) =>
          article.article_name.toLowerCase().includes(query) ||
          (article.category && article.category.toLowerCase().includes(query)) ||
          article.cost_per_unit.toString().toLowerCase().includes(query)
      );
    }

    // Item type filter
    if (itemTypeFilter !== 'all') {
      filtered = filtered.filter((article) => article.item_type === itemTypeFilter);
    }

    // Category filter
    if (categoryFilter !== 'all') {
      filtered = filtered.filter((article) => article.category === categoryFilter);
    }

    // Master category filter
    if (masterCategoryFilter !== 'all') {
      filtered = filtered.filter((article) => article.master_category === masterCategoryFilter);
    }

    // Date filter
    if (dateFilter.start || dateFilter.end) {
      filtered = filtered.filter((article) => {
        if (!article.created_at) return false;
        
        const recordDate = new Date(article.created_at);
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

    // Sorting
    if (sortColumn) {
      filtered.sort((a, b) => {
        let aValue: any;
        let bValue: any;

        switch (sortColumn) {
          case 'articleName':
            aValue = a.article_name || '';
            bValue = b.article_name || '';
            break;
          case 'costPerUnit':
            aValue = a.cost_per_unit || 0;
            bValue = b.cost_per_unit || 0;
            break;
          case 'itemType':
            aValue = a.item_type || '';
            bValue = b.item_type || '';
            break;
          case 'category':
            aValue = a.category || '';
            bValue = b.category || '';
            break;
          case 'masterCategory':
            aValue = a.master_category || '';
            bValue = b.master_category || '';
            break;
          case 'createdAt':
            aValue = a.created_at ? new Date(a.created_at).getTime() : 0;
            bValue = b.created_at ? new Date(b.created_at).getTime() : 0;
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

    setFilteredArticles(filtered);
  };

  // Handle sort
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

  // Get sort icon for column header - always show indicators
  const getSortIcon = (column: string) => {
    if (sortColumn === column) {
      // Show active sort direction
      return sortDirection === 'asc' ? '↑' : '↓';
    }
    // Show both arrows (lighter color) to indicate sortable
    return '⇅';
  };

  // Get unique item types
  const getItemTypes = (): string[] => {
    const types = new Set(articles.map((a) => a.item_type).filter(Boolean));
    return Array.from(types).sort();
  };

  // Get unique categories
  const getCategories = (): string[] => {
    const categories = new Set(
      articles.map((a) => a.category).filter((c): c is string => Boolean(c))
    );
    return Array.from(categories).sort();
  };

  // Get unique master categories
  const getMasterCategories = (): string[] => {
    const masterCategories = new Set(
      articles.map((a) => a.master_category).filter((c): c is string => Boolean(c))
    );
    return Array.from(masterCategories).sort();
  };

  const resetForm = () => {
    setFormData({
      article_name: '',
      article_name_tk: '',
      cost_per_unit: 0,
      item_type: 'Article',
      category: '',
      master_category: '',
    });
    setErrors({});
    setEditingId(null);
  };

  const handleAdd = () => {
    resetForm();
    setIsFormMode(true);
  };

  const handleEdit = (article: ArticleRecord) => {
    setFormData({
      article_name: article.article_name,
      article_name_tk: article.article_name_tk || '',
      cost_per_unit: article.cost_per_unit,
      item_type: article.item_type,
      category: article.category || '',
      master_category: article.master_category || '',
    });
    setEditingId(article.id);
    setIsFormMode(true);
  };

  const handleCancel = () => {
    resetForm();
    setIsFormMode(false);
  };

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!formData.article_name.trim()) {
      newErrors.article_name = 'Article name is required';
    }

    if (formData.cost_per_unit < 0) {
      newErrors.cost_per_unit = 'Cost per unit cannot be negative';
    }

    if (!formData.item_type) {
      newErrors.item_type = 'Item type is required';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSave = async () => {
    if (!validateForm()) {
      return;
    }

    if (isSaving) {
      return; // Prevent multiple clicks
    }

    setSaving(true);
    try {
      if (editingId) {
        await updateArticle(editingId, formData);
      } else {
        await createArticle(formData);
      }
      await loadArticles();
      resetForm();
      setIsFormMode(false);
      showSuccess(editingId ? 'Article updated successfully' : 'Article created successfully');
    } catch (error: any) {
      console.error('Failed to save article:', error);
      showError(error.message || 'Failed to save article. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string, articleName: string) => {
    setConfirmDialog({
      isOpen: true,
      title: 'Delete Article',
      message: `Are you sure you want to delete article "${articleName}"? This action cannot be undone.`,
      type: 'danger',
      onConfirm: async () => {
        setConfirmDialog({ ...confirmDialog, isOpen: false });
        try {
          await deleteArticle(id);
          await loadArticles();
          showSuccess('Article deleted successfully');
        } catch (error: any) {
          console.error('Failed to delete article:', error);
          showError(error.message || 'Failed to delete article. Please try again.');
        }
      },
    });
  };

  const clearFilters = () => {
    setSearchQuery('');
    setItemTypeFilter('all');
    setCategoryFilter('all');
    setMasterCategoryFilter('all');
    setDateFilter({ start: null, end: null });
  };

  const hasActiveFilters =
    searchQuery.trim() !== '' ||
    itemTypeFilter !== 'all' ||
    categoryFilter !== 'all' ||
    masterCategoryFilter !== 'all' ||
    dateFilter.start !== null ||
    dateFilter.end !== null;

  const handleExport = async () => {
    try {
      const exportData = filteredArticles
        .filter((article) => !article.combo)
        .map((article) => ({
        article_name: article.article_name,
        cost_per_unit: article.cost_per_unit,
        item_type: article.item_type,
        category: article.category || '',
        master_category: article.master_category || '',
        is_active: article.is_active ? 'Active' : 'Inactive',
        created_at: article.created_at ? new Date(article.created_at).toLocaleDateString() : '',
      }));

      exportToCSV(exportData, 'articles', [
        'article_name',
        'cost_per_unit',
        'item_type',
        'category',
        'master_category',
        'is_active',
        'created_at',
      ], showWarning);

      // Log export action
      if (user) {
        await logAction(user.id, 'EXPORT', 'article', null, {
          exported_count: exportData.length,
          filters_applied: hasActiveFilters,
        });
      }
      showSuccess(`Exported ${exportData.length} articles successfully`);
    } catch (error) {
      console.error('Error exporting articles:', error);
      showError('Failed to export articles. Please try again.');
    }
  };

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
        <Package className="w-8 h-8 text-blue-600 dark:text-blue-400" />
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Article Management
        </h1>
        </div>
        {!isFormMode && (
          <div className="flex items-center gap-3">
            {canExport() && (
              <button
                onClick={handleExport}
                className="flex items-center gap-2 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              >
                <Download className="w-4 h-4" />
                Export CSV
              </button>
            )}
            <button
              onClick={() => loadArticles()}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              <span className="hidden sm:inline">Refresh</span>
            </button>
            {canCreate() && (
              <button
                onClick={handleAdd}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                <Plus className="w-4 h-4" />
                Add Article
              </button>
            )}
          </div>
        )}
      </div>

      {isFormMode ? (
        <div className={`bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700 mb-6 ${isSaving ? 'pointer-events-none opacity-50' : ''}`}>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-6">
            {editingId ? 'Edit Article' : 'Add New Article'}
          </h2>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Article Name <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={formData.article_name}
                onChange={(e) =>
                  setFormData({ ...formData, article_name: e.target.value })
                }
                className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                placeholder="Enter article name"
              />
              {errors.article_name && (
                <p className="mt-1 text-sm text-red-600 dark:text-red-400">
                  {errors.article_name}
                </p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Article Name (Token)
              </label>
              <input
                type="text"
                value={formData.article_name_tk}
                onChange={(e) =>
                  setFormData({ ...formData, article_name_tk: e.target.value })
                }
                className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                placeholder="Enter short form/token name (optional)"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Cost Per Unit <span className="text-red-500">*</span>
                </label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={formData.cost_per_unit}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      cost_per_unit: parseFloat(e.target.value) || 0,
                    })
                  }
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
                {errors.cost_per_unit && (
                  <p className="mt-1 text-sm text-red-600 dark:text-red-400">
                    {errors.cost_per_unit}
                  </p>
                )}
      </div>
      
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Item Type <span className="text-red-500">*</span>
                </label>
                <select
                  value={formData.item_type}
                  onChange={(e) =>
                    setFormData({ ...formData, item_type: e.target.value })
                  }
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                >
                  <option value="Article">Article</option>
                  <option value="Aid">Aid</option>
                  <option value="Project">Project</option>
                </select>
                {errors.item_type && (
                  <p className="mt-1 text-sm text-red-600 dark:text-red-400">
                    {errors.item_type}
                  </p>
                )}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Category
              </label>
              <div className="relative" ref={categoryDropdownRef}>
                <input
                  type="text"
                  value={formData.category}
                  onChange={(e) => {
                    setFormData({ ...formData, category: e.target.value });
                    setCategoryDropdownOpen(true);
                  }}
                  onFocus={() => setCategoryDropdownOpen(true)}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  placeholder="Enter category (optional)"
                />
                {categoryDropdownOpen && getCategories().length > 0 && (
                  <div className="absolute z-50 w-full mt-1 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                    {getCategories()
                      .filter((cat) =>
                        cat.toLowerCase().includes(formData.category.toLowerCase())
                      )
                      .map((category) => (
                        <button
                          key={category}
                          type="button"
                          onClick={() => {
                            setFormData({ ...formData, category });
                            setCategoryDropdownOpen(false);
                          }}
                          className="w-full px-4 py-2 text-left text-sm text-gray-900 dark:text-white hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                        >
                          {category}
                        </button>
                      ))}
                    {getCategories().filter((cat) =>
                      cat.toLowerCase().includes(formData.category.toLowerCase())
                    ).length === 0 && formData.category && (
                      <div className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400">
                        No matching categories. Press Enter to create new.
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Master Category
              </label>
              <div className="relative" ref={masterCategoryDropdownRef}>
                <input
                  type="text"
                  value={formData.master_category}
                  onChange={(e) => {
                    setFormData({ ...formData, master_category: e.target.value });
                    setMasterCategoryDropdownOpen(true);
                  }}
                  onFocus={() => setMasterCategoryDropdownOpen(true)}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  placeholder="Enter master category (optional)"
                />
                {masterCategoryDropdownOpen && getMasterCategories().length > 0 && (
                  <div className="absolute z-50 w-full mt-1 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                    {getMasterCategories()
                      .filter((cat) =>
                        cat.toLowerCase().includes(formData.master_category.toLowerCase())
                      )
                      .map((masterCategory) => (
                        <button
                          key={masterCategory}
                          type="button"
                          onClick={() => {
                            setFormData({ ...formData, master_category: masterCategory });
                            setMasterCategoryDropdownOpen(false);
                          }}
                          className="w-full px-4 py-2 text-left text-sm text-gray-900 dark:text-white hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                        >
                          {masterCategory}
                        </button>
                      ))}
                    {getMasterCategories().filter((cat) =>
                      cat.toLowerCase().includes(formData.master_category.toLowerCase())
                    ).length === 0 && formData.master_category && (
                      <div className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400">
                        No matching master categories. Press Enter to create new.
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            <div className="flex gap-2 pt-4">
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
              <button
                onClick={handleCancel}
                disabled={isSaving}
                className="flex items-center gap-2 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <X className="w-4 h-4" />
                Cancel
              </button>
            </div>
          </div>
        </div>
      ) : (
        <>
          {/* Filters */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 border border-gray-200 dark:border-gray-700 mb-6">
            <div className="flex items-center gap-2 mb-4">
              <Filter className="w-5 h-5 text-gray-500 dark:text-gray-400" />
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">Filters</h3>
              {hasActiveFilters && (
                <button
                  onClick={clearFilters}
                  className="ml-auto text-sm text-blue-600 dark:text-blue-400 hover:underline"
                >
                  Clear All
                </button>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3 items-end">
              <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Search
                </label>
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search..."
                    className="w-full pl-10 pr-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                  />
                </div>
              </div>
              <div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Item Type
                  </label>
                  <select
                    value={itemTypeFilter}
                    onChange={(e) => setItemTypeFilter(e.target.value)}
                    className="w-full px-2.5 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-xs"
                  >
                    <option value="all">All Types</option>
                    {getItemTypes().map((type) => (
                      <option key={type} value={type}>
                        {type}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Category
                </label>
                <select
                  value={categoryFilter}
                  onChange={(e) => setCategoryFilter(e.target.value)}
                  className="w-full px-2.5 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-xs"
                >
                  <option value="all">All Categories</option>
                  {getCategories().map((category) => (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Master Category
                </label>
                <select
                  value={masterCategoryFilter}
                  onChange={(e) => setMasterCategoryFilter(e.target.value)}
                  className="w-full px-2.5 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-xs"
                >
                  <option value="all">All Master Categories</option>
                  {getMasterCategories().map((masterCategory) => (
                    <option key={masterCategory} value={masterCategory}>
                      {masterCategory}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Date Range
                </label>
                <div className="flex items-center gap-1.5">
                  <input
                    type="date"
                    value={dateFilter.start || ''}
                    onChange={(e) => setDateFilter({ ...dateFilter, start: e.target.value || null })}
                    className="w-full min-w-0 px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-xs"
                  />
                  <span className="text-xs text-gray-500 dark:text-gray-400 flex-shrink-0">to</span>
                  <input
                    type="date"
                    value={dateFilter.end || ''}
                    onChange={(e) => setDateFilter({ ...dateFilter, end: e.target.value || null })}
                    min={dateFilter.start || undefined}
                    className="w-full min-w-0 px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-xs"
                  />
                  {(dateFilter.start || dateFilter.end) && (
                    <button
                      onClick={() => setDateFilter({ start: null, end: null })}
                      className="p-1.5 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 flex-shrink-0"
                      title="Clear date filter"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Articles Table */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700 overflow-hidden">
            {loading ? (
              <div className="text-center py-12 text-gray-500 dark:text-gray-400">
                <Loader2 className="animate-spin h-8 w-8 mx-auto mb-4" />
                Loading articles...
              </div>
            ) : error ? (
              <div className="text-center py-12">
                <div className="text-red-600 dark:text-red-400 mb-4">{error}</div>
                <button
                  onClick={handleRetry}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                >
                  Retry
                </button>
              </div>
            ) : filteredArticles.length === 0 ? (
              <div className="text-center py-12 text-gray-500 dark:text-gray-400">
                {hasActiveFilters
                  ? 'No articles found matching the filters'
                  : 'No articles found. Add your first article to get started.'}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse">
                  <thead className="bg-gray-50 dark:bg-gray-800">
                    <tr>
                      <th 
                        className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                        onClick={() => handleSort('articleName')}
                      >
                        <div className="flex items-center gap-1">
                          Article Name
                          <span className={`text-xs ${sortColumn === 'articleName' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                            {getSortIcon('articleName')}
                          </span>
                        </div>
                      </th>
                      <th 
                        className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                        onClick={() => handleSort('costPerUnit')}
                      >
                        <div className="flex items-center gap-1">
                          Cost Per Unit
                          <span className={`text-xs ${sortColumn === 'costPerUnit' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                            {getSortIcon('costPerUnit')}
                          </span>
                        </div>
                      </th>
                      <th 
                        className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                        onClick={() => handleSort('itemType')}
                      >
                        <div className="flex items-center gap-1">
                          Item Type
                          <span className={`text-xs ${sortColumn === 'itemType' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                            {getSortIcon('itemType')}
                          </span>
                        </div>
                      </th>
                      <th 
                        className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                        onClick={() => handleSort('category')}
                      >
                        <div className="flex items-center gap-1">
                          Category
                          <span className={`text-xs ${sortColumn === 'category' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                            {getSortIcon('category')}
                          </span>
                        </div>
                      </th>
                      <th 
                        className="px-4 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                        onClick={() => handleSort('masterCategory')}
                      >
                        <div className="flex items-center gap-1">
                          Master Category
                          <span className={`text-xs ${sortColumn === 'masterCategory' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                            {getSortIcon('masterCategory')}
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
                    </tr>
                  </thead>
                  <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-700">
                    {filteredArticles.map((article) => (
                      <tr
                        key={article.id}
                        className="hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                      >
                        <td className="px-4 py-3 text-sm text-gray-900 dark:text-white font-medium">
                          {article.article_name}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-900 dark:text-white">
                          {CURRENCY_SYMBOL}{article.cost_per_unit.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                          {article.item_type}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                          {article.category || '-'}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                          {article.master_category || '-'}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                          {article.created_at ? new Date(article.created_at).toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '-'}
                        </td>
                        <td className="px-4 py-3 text-sm">
                          <div className="flex items-center gap-2">
                            {canUpdate() && (
                              <button
                                onClick={() => handleEdit(article)}
                                className="p-1.5 text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/30 rounded transition-colors"
                                aria-label="Edit"
                                title="Edit"
                              >
                                <Edit2 className="w-4 h-4" />
                              </button>
                            )}
                            {canDelete() && (
                              <button
                                onClick={() => handleDelete(article.id, article.article_name)}
                                className="p-1.5 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/30 rounded transition-colors"
                                aria-label="Delete"
                                title="Delete"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {!loading && filteredArticles.length > 0 && (
            <div className="mt-4 text-sm text-gray-600 dark:text-gray-400">
              Showing {filteredArticles.length} of {articles.length} article(s)
            </div>
          )}
        </>
      )}

      <ConfirmDialog
        isOpen={confirmDialog.isOpen}
        title={confirmDialog.title}
        message={confirmDialog.message}
        type={confirmDialog.type}
        onConfirm={confirmDialog.onConfirm}
        onCancel={() => setConfirmDialog({ ...confirmDialog, isOpen: false })}
      />
    </div>
  );
};

export default ArticleManagement;
