import React, { useState, useEffect } from 'react';
import { FileText, Download, Filter, Loader2 } from 'lucide-react';
import { useRBAC } from '../contexts/RBACContext';
import {
  fetchAuditLogs,
  getAuditLogsCount,
  type AuditLogWithUser,
  type ActionType,
  type EntityType,
} from '../services/auditLogService';
import { exportToCSV } from '../utils/csvExport';
import { logAction } from '../services/auditLogService';
import { useAuth } from '../contexts/AuthContext';
import { useNotifications } from '../contexts/NotificationContext';

const AuditLogs: React.FC = () => {
  const { user } = useAuth();
  const { isAdmin } = useRBAC();
  const { showError, showSuccess, showWarning } = useNotifications();
  const [logs, setLogs] = useState<AuditLogWithUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [totalCount, setTotalCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize] = useState(50);
  const [filters, setFilters] = useState({
    actionType: '' as ActionType | '',
    entityType: '' as EntityType | '',
    startDate: '',
    endDate: '',
  });
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    if (isAdmin) {
      loadLogs();
    }
  }, [isAdmin, currentPage, filters]);

  const loadLogs = async () => {
    try {
      setLoading(true);
      const offset = (currentPage - 1) * pageSize;
      
      const filterParams: any = {
        limit: pageSize,
        offset,
      };

      if (filters.actionType) {
        filterParams.actionType = filters.actionType;
      }
      if (filters.entityType) {
        filterParams.entityType = filters.entityType;
      }
      if (filters.startDate) {
        filterParams.startDate = filters.startDate;
      }
      if (filters.endDate) {
        filterParams.endDate = filters.endDate;
      }

      const [logsData, count] = await Promise.all([
        fetchAuditLogs(filterParams),
        getAuditLogsCount(filterParams),
      ]);

      setLogs(logsData);
      setTotalCount(count);
    } catch (error) {
      console.error('Error loading audit logs:', error);
      showError('Failed to load audit logs. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async () => {
    try {
      // Fetch all logs matching current filters (without pagination)
      const filterParams: any = {};
      if (filters.actionType) filterParams.actionType = filters.actionType;
      if (filters.entityType) filterParams.entityType = filters.entityType;
      if (filters.startDate) filterParams.startDate = filters.startDate;
      if (filters.endDate) filterParams.endDate = filters.endDate;

      const allLogs = await fetchAuditLogs(filterParams);

      const exportData = allLogs.map((log) => ({
        timestamp: new Date(log.created_at).toLocaleString(),
        user: log.app_users?.name || log.app_users?.email || 'System',
        action_type: log.action_type,
        entity_type: log.entity_type,
        entity_id: log.entity_id || '',
        details: JSON.stringify(log.details),
        ip_address: log.ip_address || '',
      }));

      exportToCSV(exportData, 'audit-logs', [
        'timestamp',
        'user',
        'action_type',
        'entity_type',
        'entity_id',
        'details',
        'ip_address',
      ], showWarning);

      // Log export action
      if (user) {
        await logAction(user.id, 'EXPORT', 'system', null, {
          exported_count: exportData.length,
          filters_applied: Object.keys(filters).filter(k => filters[k as keyof typeof filters] !== ''),
        });
      }
      showSuccess(`Exported ${exportData.length} audit logs successfully`);
    } catch (error) {
      console.error('Error exporting audit logs:', error);
      showError('Failed to export audit logs. Please try again.');
    }
  };

  const clearFilters = () => {
    setFilters({
      actionType: '' as ActionType | '',
      entityType: '' as EntityType | '',
      startDate: '',
      endDate: '',
    });
    setCurrentPage(1);
  };

  const hasActiveFilters = Object.values(filters).some((v) => v !== '');

  const totalPages = Math.ceil(totalCount / pageSize);

  if (!isAdmin) {
    return (
      <div className="p-6">
        <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
          <p className="text-yellow-800 dark:text-yellow-200">You don't have permission to view this page.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-3">
          <FileText className="w-8 h-8 text-blue-600 dark:text-blue-400" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Audit Logs</h1>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleExport}
            className="flex items-center space-x-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 px-4 py-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
          >
            <Download className="w-4 h-4" />
            <span>Export CSV</span>
          </button>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className="flex items-center space-x-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 px-4 py-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
          >
            <Filter className="w-4 h-4" />
            <span>Filters</span>
          </button>
        </div>
      </div>

      {/* Filters */}
      {showFilters && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 border border-gray-200 dark:border-gray-700 mb-6">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">Filter Logs</h3>
            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                className="text-sm text-blue-600 dark:text-blue-400 hover:underline"
              >
                Clear All
              </button>
            )}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                Action Type
              </label>
              <select
                value={filters.actionType}
                onChange={(e) => {
                  setFilters({ ...filters, actionType: e.target.value as ActionType | '' });
                  setCurrentPage(1);
                }}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
              >
                <option value="">All Actions</option>
                <option value="CREATE">Create</option>
                <option value="UPDATE">Update</option>
                <option value="DELETE">Delete</option>
                <option value="LOGIN">Login</option>
                <option value="LOGOUT">Logout</option>
                <option value="EXPORT">Export</option>
                <option value="STATUS_CHANGE">Status Change</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                Entity Type
              </label>
              <select
                value={filters.entityType}
                onChange={(e) => {
                  setFilters({ ...filters, entityType: e.target.value as EntityType | '' });
                  setCurrentPage(1);
                }}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
              >
                <option value="">All Entities</option>
                <option value="article">Article</option>
                <option value="master_entry">Master Entry</option>
                <option value="order">Order</option>
                <option value="user">User</option>
                <option value="district_beneficiary">District Beneficiary</option>
                <option value="public_beneficiary">Public Beneficiary</option>
                <option value="institution_beneficiary">Institution Beneficiary</option>
                <option value="system">System</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                Start Date
              </label>
              <input
                type="date"
                value={filters.startDate}
                onChange={(e) => {
                  setFilters({ ...filters, startDate: e.target.value });
                  setCurrentPage(1);
                }}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                End Date
              </label>
              <input
                type="date"
                value={filters.endDate}
                onChange={(e) => {
                  setFilters({ ...filters, endDate: e.target.value });
                  setCurrentPage(1);
                }}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
              />
            </div>
          </div>
        </div>
      )}

      {/* Logs Table */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700 overflow-hidden">
        {loading ? (
          <div className="flex justify-center items-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
          </div>
        ) : logs.length === 0 ? (
          <div className="text-center py-12 text-gray-500 dark:text-gray-400">
            <FileText className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p>No audit logs found.</p>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="bg-gray-50 dark:bg-gray-700">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                      Timestamp
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                      User
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                      Action
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                      Entity
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                      Entity ID
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                      Details
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                  {logs.map((log) => (
                    <tr key={log.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {new Date(log.created_at).toLocaleString()}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">
                        {log.app_users?.name || log.app_users?.email || 'System'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`px-2 py-1 text-xs font-semibold rounded-full ${
                          log.action_type === 'CREATE'
                            ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                            : log.action_type === 'UPDATE'
                            ? 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200'
                            : log.action_type === 'DELETE'
                            ? 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
                            : log.action_type === 'LOGIN' || log.action_type === 'LOGOUT'
                            ? 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200'
                            : log.action_type === 'EXPORT'
                            ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200'
                            : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200'
                        }`}>
                          {log.action_type}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400 capitalize">
                        {log.entity_type.replace('_', ' ')}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400 font-mono text-xs">
                        {log.entity_id ? log.entity_id.substring(0, 8) + '...' : '-'}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400 max-w-md">
                        <div className="space-y-1">
                          {log.details.entity_name && (
                            <div className="font-medium text-gray-900 dark:text-white">
                              {log.details.entity_name}
                            </div>
                          )}
                          {log.action_type === 'UPDATE' && log.details.old_values && log.details.new_values && (
                            <div className="text-xs space-y-0.5">
                              {Object.keys(log.details.new_values).map((key) => (
                                <div key={key} className="flex items-start gap-2">
                                  <span className="text-gray-400 dark:text-gray-500">{key}:</span>
                                  <span className="text-red-600 dark:text-red-400 line-through">
                                    {String(log.details.old_values[key] ?? 'N/A')}
                                  </span>
                                  <span className="text-gray-400 dark:text-gray-500">→</span>
                                  <span className="text-green-600 dark:text-green-400 font-medium">
                                    {String(log.details.new_values[key] ?? 'N/A')}
                                  </span>
                                </div>
                              ))}
                            </div>
                          )}
                          {log.action_type === 'CREATE' && log.details.new_values && (
                            <div className="text-xs text-green-600 dark:text-green-400">
                              Created: {Object.keys(log.details.new_values).join(', ')}
                            </div>
                          )}
                          {log.action_type === 'DELETE' && log.details.deleted_values && (
                            <div className="text-xs text-red-600 dark:text-red-400">
                              Deleted: {Object.keys(log.details.deleted_values).join(', ')}
                            </div>
                          )}
                          {log.action_type === 'STATUS_CHANGE' && (
                            <div className="text-xs">
                              <span className="text-red-600 dark:text-red-400 line-through">
                                {String(log.details.previous_status ?? 'N/A')}
                              </span>
                              <span className="text-gray-400 dark:text-gray-500 mx-1">→</span>
                              <span className="text-green-600 dark:text-green-400 font-medium">
                                {String(log.details.new_status ?? 'N/A')}
                              </span>
                            </div>
                          )}
                          {!log.details.old_values && !log.details.new_values && !log.details.deleted_values && log.action_type !== 'STATUS_CHANGE' && (
                            <div className="text-xs truncate max-w-xs">
                              {JSON.stringify(log.details).substring(0, 80)}
                              {JSON.stringify(log.details).length > 80 ? '...' : ''}
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="bg-gray-50 dark:bg-gray-700 px-6 py-4 flex items-center justify-between border-t border-gray-200 dark:border-gray-600">
                <div className="text-sm text-gray-700 dark:text-gray-300">
                  Showing {(currentPage - 1) * pageSize + 1} to {Math.min(currentPage * pageSize, totalCount)} of {totalCount} logs
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                    disabled={currentPage === 1}
                    className="px-3 py-1 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Previous
                  </button>
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    Page {currentPage} of {totalPages}
                  </span>
                  <button
                    onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                    disabled={currentPage === totalPages}
                    className="px-3 py-1 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default AuditLogs;
