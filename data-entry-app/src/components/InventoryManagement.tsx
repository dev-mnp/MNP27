import React, { useState, useEffect, useRef } from 'react';
import { Warehouse, RefreshCw, Download } from 'lucide-react';
import { getConsolidatedOrdersWithTracking, type ConsolidatedArticle } from '../services/orderConsolidationService';
import { exportToCSV } from '../utils/csvExport';
import { logAction } from '../services/auditLogService';
import { useAuth } from '../contexts/AuthContext';
import { useNotifications } from '../contexts/NotificationContext';
import { useRBAC } from '../contexts/RBACContext';
import { ConfirmDialog } from './ConfirmDialog';

const InventoryManagement: React.FC = () => {
  const { user, isAuthenticated, isRestoringSession } = useAuth();
  const { canExport } = useRBAC();
  const { showError, showSuccess, showWarning } = useNotifications();
  
  // Log when component mounts
  useEffect(() => {
    console.debug('InventoryManagement: Component mounted');
    isMountedRef.current = true;
    return () => {
      console.debug('InventoryManagement: Component unmounting');
      isMountedRef.current = false;
    };
  }, []);
  const [consolidatedOrders, setConsolidatedOrders] = useState<ConsolidatedArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [itemTypeFilter, setItemTypeFilter] = useState<'all' | 'Article' | 'Aid' | 'Project'>('all');
  
  // Sorting
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
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

  // Track loading state to prevent duplicate fetches
  const isLoadingRef = useRef(false);
  const isMountedRef = useRef(true);

  useEffect(() => {
    if (!isAuthenticated || isRestoringSession) {
      return;
    }
    
    // Prevent duplicate calls
    if (isLoadingRef.current) {
      return;
    }
    
    console.debug('InventoryManagement: Both conditions met, calling loadConsolidatedOrders...');
    loadConsolidatedOrders();
    
    return () => {
      // Reset loading flag on unmount so remount can fetch again
      isLoadingRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, isRestoringSession]); // loadConsolidatedOrders is stable, no need to include it

  const loadConsolidatedOrders = async (isRetry: boolean = false) => {
    // Prevent duplicate fetches
    if (isLoadingRef.current) {
      console.debug('InventoryManagement: loadConsolidatedOrders already in progress, skipping');
      return;
    }
    
    isLoadingRef.current = true;
    const fetchStartTime = Date.now();
    
    // Add timeout protection at component level (30 seconds)
    const timeoutId = setTimeout(() => {
      if (isLoadingRef.current) {
        isLoadingRef.current = false;
        const fetchDuration = Date.now() - fetchStartTime;
        console.error(`InventoryManagement: loadConsolidatedOrders timed out after ${fetchDuration}ms`);
        if (isMountedRef.current) {
          setLoading(false);
          setError('Request timed out. Please check your connection and try again.');
        }
      }
    }, 30000);
    
    try {
      if (isRetry) {
        console.debug(`InventoryManagement: Retrying loadConsolidatedOrders (attempt ${retryCount + 1})...`);
      } else {
        console.debug('InventoryManagement: loadConsolidatedOrders called, starting fetch...');
      }
      setLoading(true);
      setError(null);
      
      const data = await getConsolidatedOrdersWithTracking();
      clearTimeout(timeoutId);
      
      const fetchDuration = Date.now() - fetchStartTime;
      console.debug(`InventoryManagement: Consolidated orders fetched successfully in ${fetchDuration}ms, count: ${data?.articles?.length || 0}`);
      setConsolidatedOrders(data.articles);
      setRetryCount(0); // Reset retry count on success
    } catch (error: any) {
      clearTimeout(timeoutId);
      const fetchDuration = Date.now() - fetchStartTime;
      console.error(`InventoryManagement: Failed to load consolidated orders after ${fetchDuration}ms:`, error);
      
      const errorMessage = error?.message || 'Failed to load consolidated orders. Please try again.';
      setError(errorMessage);
      
      // Don't show alert if it's a timeout (already handled)
      if (!errorMessage.includes('timeout')) {
        alert(errorMessage);
      }
    } finally {
      isLoadingRef.current = false;
      setLoading(false);
      const fetchDuration = Date.now() - fetchStartTime;
      console.debug(`InventoryManagement: loadConsolidatedOrders completed in ${fetchDuration}ms`);
    }
  };
  
  const handleRetry = () => {
    setRetryCount(prev => prev + 1);
    loadConsolidatedOrders(true);
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

  // Filter and sort articles
  const getFilteredAndSortedArticles = (): ConsolidatedArticle[] => {
    let filtered = consolidatedOrders.filter(article => {
      const matchesSearch = article.articleName.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesItemType = itemTypeFilter === 'all' || article.itemType === itemTypeFilter;
      return matchesSearch && matchesItemType;
    });

    // Sorting
    if (sortColumn) {
      filtered.sort((a, b) => {
        let aValue: any;
        let bValue: any;

        switch (sortColumn) {
          case 'articleName':
            aValue = a.articleName || '';
            bValue = b.articleName || '';
            break;
          case 'needed':
            aValue = a.totalQuantity || 0;
            bValue = b.totalQuantity || 0;
            break;
          case 'ordered':
            aValue = a.quantityOrdered || 0;
            bValue = b.quantityOrdered || 0;
            break;
          case 'pending':
            aValue = a.quantityPending || 0;
            bValue = b.quantityPending || 0;
            break;
          case 'district':
            aValue = a.breakdown.district || 0;
            bValue = b.breakdown.district || 0;
            break;
          case 'public':
            aValue = a.breakdown.public || 0;
            bValue = b.breakdown.public || 0;
            break;
          case 'institutions':
            aValue = a.breakdown.institutions || 0;
            bValue = b.breakdown.institutions || 0;
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

  const filteredArticles = getFilteredAndSortedArticles();

  // Calculate metrics by item type
  const articles = consolidatedOrders.filter(a => a.itemType === 'Article');
  const aids = consolidatedOrders.filter(a => a.itemType === 'Aid');
  const projects = consolidatedOrders.filter(a => a.itemType === 'Project');
  
  const articlesNeeded = articles.reduce((sum, a) => sum + a.totalQuantity, 0);
  const articlesOrdered = articles.reduce((sum, a) => sum + (a.quantityOrdered || 0), 0);
  const articlesPendingCount = articles.reduce((sum, a) => {
    const pending = a.quantityPending || 0;
    return sum + (pending > 0 ? pending : 0);
  }, 0);
  const articlesExcessCount = articles.reduce((sum, a) => {
    const pending = a.quantityPending || 0;
    return sum + (pending < 0 ? Math.abs(pending) : 0);
  }, 0);
  
  const aidsNeeded = aids.reduce((sum, a) => sum + a.totalQuantity, 0);
  const aidsOrdered = aids.reduce((sum, a) => sum + (a.quantityOrdered || 0), 0);
  const aidsPending = aids.reduce((sum, a) => sum + (a.quantityPending || 0), 0);
  
  const projectsNeeded = projects.reduce((sum, a) => sum + a.totalQuantity, 0);
  const projectsOrdered = projects.reduce((sum, a) => sum + (a.quantityOrdered || 0), 0);
  const projectsPending = projects.reduce((sum, a) => sum + (a.quantityPending || 0), 0);

  const handleExport = async () => {
    try {
      const exportData = filteredArticles.map((article) => ({
        'Article Name': article.articleName,
        'Total Quantity Needed': article.totalQuantity,
        'Quantity Ordered': article.quantityOrdered || 0,
        'Quantity Pending': article.quantityPending || 0,
        'District': article.breakdown.district,
        'Public': article.breakdown.public,
        'Institutions': article.breakdown.institutions,
      }));

      exportToCSV(exportData, 'inventory-orders', [
        'Article Name',
        'Total Quantity Needed',
        'Quantity Ordered',
        'Quantity Pending',
        'District',
        'Public',
        'Institutions',
      ], showWarning);

      // Log export action
      if (user) {
        await logAction(user.id, 'EXPORT', 'order', null, {
          exported_count: exportData.length,
          search_query: searchQuery || null,
        });
      }
      showSuccess(`Exported ${exportData.length} inventory items successfully`);
    } catch (error) {
      console.error('Error exporting inventory:', error);
      showError('Failed to export inventory. Please try again.');
    }
  };

  return (
    <div className="p-4 sm:p-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
        <div className="flex items-center gap-3">
          <Warehouse className="w-8 h-8 text-blue-600 dark:text-blue-400" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Order Management
          </h1>
        </div>
        <div className="flex items-center gap-2">
          {canExport() && (
            <button
              onClick={handleExport}
              className="flex items-center gap-2 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            >
              <Download className="w-4 h-4" />
              <span className="hidden sm:inline">Export CSV</span>
            </button>
          )}
          <button
            onClick={() => loadConsolidatedOrders()}
            className="flex items-center gap-2 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            <span className="hidden sm:inline">Refresh</span>
          </button>
        </div>
      </div>

      {/* Summary Cards by Item Type */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {/* Articles Card */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5 border border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-blue-600 dark:text-blue-400">Articles</h3>
            <span className="text-sm font-medium text-gray-500 dark:text-gray-400">{articles.length} items</span>
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-400">Needed</span>
              <span className="text-lg font-bold text-gray-900 dark:text-white">
                {articlesNeeded.toLocaleString('en-IN')}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-400">Ordered</span>
              <span className="text-lg font-bold text-blue-600 dark:text-blue-400">
                {articlesOrdered.toLocaleString('en-IN')}
              </span>
            </div>
            <div className="flex items-center justify-between pt-2 border-t border-gray-200 dark:border-gray-700">
              <span className="text-sm font-medium text-gray-600 dark:text-gray-400">Pending</span>
              <span className={`text-lg font-bold ${articlesPendingCount > 0 ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'}`}>
                {articlesPendingCount.toLocaleString('en-IN')}
              </span>
            </div>
            <div className="flex items-center justify-between pt-1">
              <span className="text-sm font-medium text-gray-600 dark:text-gray-400">Excess</span>
              <span className="text-lg font-bold text-green-600 dark:text-green-400">
                {articlesExcessCount.toLocaleString('en-IN')}
              </span>
            </div>
          </div>
        </div>

        {/* Aids Card */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5 border border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-green-600 dark:text-green-400">Aids</h3>
            <span className="text-sm font-medium text-gray-500 dark:text-gray-400">{aids.length} items</span>
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-400">Needed</span>
              <span className="text-lg font-bold text-gray-900 dark:text-white">
                {aidsNeeded.toLocaleString('en-IN')}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-400">Ordered</span>
              <span className="text-lg font-bold text-blue-600 dark:text-blue-400">
                {aidsOrdered.toLocaleString('en-IN')}
              </span>
            </div>
            <div className="flex items-center justify-between pt-2 border-t border-gray-200 dark:border-gray-700">
              <span className="text-sm font-medium text-gray-600 dark:text-gray-400">Pending</span>
              <span className={`text-lg font-bold ${aidsPending > 0 ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'}`}>
                {aidsPending.toLocaleString('en-IN')}
              </span>
            </div>
          </div>
        </div>

        {/* Projects Card */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5 border border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-purple-600 dark:text-purple-400">Projects</h3>
            <span className="text-sm font-medium text-gray-500 dark:text-gray-400">{projects.length} items</span>
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-400">Needed</span>
              <span className="text-lg font-bold text-gray-900 dark:text-white">
                {projectsNeeded.toLocaleString('en-IN')}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-400">Ordered</span>
              <span className="text-lg font-bold text-blue-600 dark:text-blue-400">
                {projectsOrdered.toLocaleString('en-IN')}
              </span>
            </div>
            <div className="flex items-center justify-between pt-2 border-t border-gray-200 dark:border-gray-700">
              <span className="text-sm font-medium text-gray-600 dark:text-gray-400">Pending</span>
              <span className={`text-lg font-bold ${projectsPending > 0 ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'}`}>
                {projectsPending.toLocaleString('en-IN')}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Search and Filter */}
      <div className="mb-4 flex flex-col sm:flex-row gap-4">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search articles..."
          className="flex-1 max-w-md px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
        />
        <select
          value={itemTypeFilter}
          onChange={(e) => setItemTypeFilter(e.target.value as 'all' | 'Article' | 'Aid' | 'Project')}
          className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm min-w-[150px]"
        >
          <option value="all">All Types</option>
          <option value="Article">Article</option>
          <option value="Aid">Aid</option>
          <option value="Project">Project</option>
        </select>
      </div>

      {/* Consolidated Orders Table */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700 overflow-hidden">
        {loading ? (
          <div className="text-center py-12 text-gray-500 dark:text-gray-400">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 dark:border-blue-400 mb-2"></div>
            <p>Loading consolidated orders...</p>
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
            <p>No orders found.</p>
          </div>
        ) : (
          <div>
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
                    className="px-4 py-3 text-center text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                    onClick={() => handleSort('needed')}
                  >
                    <div className="flex items-center justify-center gap-1">
                      Needed
                      <span className={`text-xs ${sortColumn === 'needed' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('needed')}
                      </span>
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-center text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                    onClick={() => handleSort('ordered')}
                  >
                    <div className="flex items-center justify-center gap-1">
                      Ordered
                      <span className={`text-xs ${sortColumn === 'ordered' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('ordered')}
                      </span>
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-center text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 select-none"
                    onClick={() => handleSort('pending')}
                  >
                    <div className="flex items-center justify-center gap-1">
                      <span className="text-red-600 dark:text-red-400">Pending</span>
                      <span>/</span>
                      <span className="text-green-600 dark:text-green-400">Excess</span>
                      <span className={`text-xs ${sortColumn === 'pending' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('pending')}
                      </span>
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-center text-xs font-medium text-blue-700 dark:text-blue-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 bg-blue-50 dark:bg-blue-900/20 cursor-pointer hover:bg-blue-100 dark:hover:bg-blue-900/30 select-none"
                    onClick={() => handleSort('district')}
                  >
                    <div className="flex items-center justify-center gap-1">
                      District
                      <span className={`text-xs ${sortColumn === 'district' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('district')}
                      </span>
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-center text-xs font-medium text-green-700 dark:text-green-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 bg-green-50 dark:bg-green-900/20 cursor-pointer hover:bg-green-100 dark:hover:bg-green-900/30 select-none"
                    onClick={() => handleSort('public')}
                  >
                    <div className="flex items-center justify-center gap-1">
                      Public
                      <span className={`text-xs ${sortColumn === 'public' ? 'text-green-600 dark:text-green-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('public')}
                      </span>
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-center text-xs font-medium text-purple-700 dark:text-purple-300 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700 bg-purple-50 dark:bg-purple-900/20 cursor-pointer hover:bg-purple-100 dark:hover:bg-purple-900/30 select-none"
                    onClick={() => handleSort('institutions')}
                  >
                    <div className="flex items-center justify-center gap-1">
                      Institutions & Others
                      <span className={`text-xs ${sortColumn === 'institutions' ? 'text-purple-600 dark:text-purple-400' : 'text-gray-400 dark:text-gray-500'}`}>
                        {getSortIcon('institutions')}
                      </span>
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-700">
                {filteredArticles.map((article) => {
                  const pending = article.quantityPending || 0;
                  
                  return (
                    <tr 
                      key={article.articleId}
                      className="hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                    >
                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-white font-medium">
                        {article.articleName}
                      </td>
                      <td className="px-4 py-3 text-sm text-center text-gray-900 dark:text-white font-semibold">
                        {article.totalQuantity.toLocaleString('en-IN')}
                      </td>
                      <td className="px-4 py-3 text-sm text-center text-blue-600 dark:text-blue-400 font-semibold">
                        {article.quantityOrdered?.toLocaleString('en-IN') || 0}
                      </td>
                      <td className={`px-4 py-3 text-sm text-center font-semibold ${pending > 0 ? 'text-red-600 dark:text-red-400' : pending < 0 ? 'text-green-600 dark:text-green-400' : 'text-gray-600 dark:text-gray-400'}`}>
                        {pending.toLocaleString('en-IN')}
                      </td>
                      <td className="px-4 py-3 text-sm text-center text-blue-600 dark:text-blue-400 font-semibold bg-blue-50 dark:bg-blue-900/20">
                        {article.breakdown.district.toLocaleString('en-IN')}
                      </td>
                      <td className="px-4 py-3 text-sm text-center text-green-600 dark:text-green-400 font-semibold bg-green-50 dark:bg-green-900/20">
                        {article.breakdown.public.toLocaleString('en-IN')}
                      </td>
                      <td className="px-4 py-3 text-sm text-center text-purple-600 dark:text-purple-400 font-semibold bg-purple-50 dark:bg-purple-900/20">
                        {article.breakdown.institutions.toLocaleString('en-IN')}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            </div>
          </div>
        )}
      </div>

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

export default InventoryManagement;
