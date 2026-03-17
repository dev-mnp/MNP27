import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Download, FileUp, RefreshCw, RotateCcw, Save } from 'lucide-react';
import { useNotifications } from '../contexts/NotificationContext';
import {
  fetchSeatAllocationRows,
  type SeatAllocationRow,
  updateSeatAllocationSequenceData,
} from '../services/seatAllocationService';
import { exportToCSV } from '../utils/csvExport';
import { SEQUENCE_2025_DEFAULT } from '../data/sequenceList2025';

type SourceMode = 'db' | 'csv';

type SequenceSourceRow = {
  sourceId?: string;
  requestedItem: string;
  tokenQuantity: number;
  rowMap: Record<string, any>;
  headers: string[];
};

type SequenceItem = {
  item: string;
};

const DEFAULT_SESSION_NAME = 'default';

const normalizeHeader = (header: string) => header.trim().toLowerCase().replace(/\s+/g, ' ');

const findHeaderName = (headers: string[], candidates: string[]): string | null => {
  const byNormalized = new Map(headers.map((h) => [normalizeHeader(h), h]));
  for (const candidate of candidates) {
    const found = byNormalized.get(normalizeHeader(candidate));
    if (found) return found;
  }
  return null;
};

const getRowCategory = (row: SequenceSourceRow): string => {
  const candidates = [
    'Master Category',
    'master category',
    'Category',
    'category',
    'Item Type',
    'ITEM TYPE',
    'item type',
  ];
  for (const key of candidates) {
    const value = row.rowMap?.[key];
    if (value !== undefined && value !== null) {
      const text = String(value).trim();
      if (text) return text;
    }
  }
  return 'Uncategorized';
};

const parseCSVRows = (text: string): string[][] => {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    const nextChar = text[i + 1];

    if (char === '"') {
      if (inQuotes && nextChar === '"') {
        field += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }

    if (char === ',' && !inQuotes) {
      row.push(field);
      field = '';
      continue;
    }

    if ((char === '\n' || char === '\r') && !inQuotes) {
      if (char === '\r' && nextChar === '\n') i++;
      row.push(field);
      if (row.some((cell) => cell.trim() !== '')) rows.push(row);
      row = [];
      field = '';
      continue;
    }

    field += char;
  }

  row.push(field);
  if (row.some((cell) => cell.trim() !== '')) rows.push(row);
  return rows;
};

const parseNumber = (value: unknown): number => {
  const raw = String(value ?? '').replace(/,/g, '').trim();
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : 0;
};

const normalizeItemName = (value: string): string =>
  value
    .toLowerCase()
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();

const tokenSet = (value: string): Set<string> =>
  new Set(
    normalizeItemName(value)
      .split(' ')
      .map((t) => t.trim())
      .filter((t) => t.length > 1)
  );

const overlapScore = (a: Set<string>, b: Set<string>): number => {
  if (!a.size || !b.size) return 0;
  let common = 0;
  a.forEach((token) => {
    if (b.has(token)) common += 1;
  });
  const denom = Math.max(a.size, b.size);
  return denom ? common / denom : 0;
};

const toDbSourceRow = (row: SeatAllocationRow): SequenceSourceRow => {
  const baseHeaders = (row.master_headers || []).filter(
    (h) => normalizeHeader(h) !== 'waiting hall quantity' && normalizeHeader(h) !== 'token quantity'
  );
  const headers = [...baseHeaders, 'Waiting Hall Quantity', 'Token Quantity'];
  const rowMap: Record<string, any> = {};

  baseHeaders.forEach((header) => {
    rowMap[header] = (row.master_row as Record<string, any> | null)?.[header] ?? '';
  });
  rowMap['Waiting Hall Quantity'] = Number(row.waiting_hall_quantity) || 0;
  rowMap['Token Quantity'] = Number(row.token_quantity) || 0;

  return {
    sourceId: row.id,
    requestedItem: row.requested_item || '',
    tokenQuantity: Number(row.token_quantity) || 0,
    rowMap,
    headers,
  };
};

const Phase2SequenceList: React.FC = () => {
  const { showError, showSuccess, showWarning } = useNotifications();
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [sourceMode, setSourceMode] = useState<SourceMode>('db');
  const [isLoadingDb, setIsLoadingDb] = useState(false);
  const [isLoadingCsv, setIsLoadingCsv] = useState(false);
  const [isSavingDb, setIsSavingDb] = useState(false);
  const [isAutoSavingDb, setIsAutoSavingDb] = useState(false);
  const [sourceFileName, setSourceFileName] = useState('');
  const [includeOnlyTokenRows, setIncludeOnlyTokenRows] = useState(true);
  const [sequenceStart, setSequenceStart] = useState(1);
  const [unassignedSearch, setUnassignedSearch] = useState('');
  const [unassignedCategoryFilter, setUnassignedCategoryFilter] = useState('all');
  const [assignedCategoryFilter, setAssignedCategoryFilter] = useState('all');
  const [sourceRows, setSourceRows] = useState<SequenceSourceRow[]>([]);

  const sequence2025Map = useMemo(
    () => new Map(SEQUENCE_2025_DEFAULT.map((item, index) => [normalizeItemName(item), index + 1])),
    []
  );

  const [assignedItems, setAssignedItems] = useState<SequenceItem[]>([]);
  const [unassignedItems, setUnassignedItems] = useState<string[]>([]);
  const [selectedLeft, setSelectedLeft] = useState<Set<string>>(new Set());
  const [selectedRight, setSelectedRight] = useState<Set<string>>(new Set());
  const [draggingItem, setDraggingItem] = useState<string | null>(null);

  const uniqueItemCount = assignedItems.length + unassignedItems.length;
  const dataRowCount = sourceRows.length;
  const categoryByItem = useMemo(() => {
    const map = new Map<string, string>();
    sourceRows.forEach((row) => {
      const item = row.requestedItem.trim();
      if (!item || map.has(item)) return;
      map.set(item, getRowCategory(row));
    });
    return map;
  }, [sourceRows]);
  const unassignedCategoryOptions = useMemo(
    () =>
      Array.from(new Set(unassignedItems.map((item) => categoryByItem.get(item) || 'Uncategorized'))).sort((a, b) =>
        a.localeCompare(b, undefined, { sensitivity: 'base' })
      ),
    [unassignedItems, categoryByItem]
  );
  const filteredUnassignedItems = useMemo(() => {
    const q = unassignedSearch.trim().toLowerCase();
    return unassignedItems.filter((item) => {
      const matchesSearch = !q || item.toLowerCase().includes(q);
      const category = categoryByItem.get(item) || 'Uncategorized';
      const matchesCategory = unassignedCategoryFilter === 'all' || category === unassignedCategoryFilter;
      return matchesSearch && matchesCategory;
    });
  }, [unassignedItems, unassignedSearch, unassignedCategoryFilter, categoryByItem]);
  const assignedCategoryOptions = useMemo(
    () =>
      Array.from(new Set(assignedItems.map((row) => categoryByItem.get(row.item) || 'Uncategorized'))).sort((a, b) =>
        a.localeCompare(b, undefined, { sensitivity: 'base' })
      ),
    [assignedItems, categoryByItem]
  );
  const filteredAssignedItems = useMemo(
    () =>
      assignedItems.filter((row) => {
        const category = categoryByItem.get(row.item) || 'Uncategorized';
        return assignedCategoryFilter === 'all' || category === assignedCategoryFilter;
      }),
    [assignedItems, categoryByItem, assignedCategoryFilter]
  );

  useEffect(() => {
    if (unassignedCategoryFilter === 'all') return;
    if (!unassignedCategoryOptions.includes(unassignedCategoryFilter)) {
      setUnassignedCategoryFilter('all');
    }
  }, [unassignedCategoryFilter, unassignedCategoryOptions]);

  useEffect(() => {
    if (assignedCategoryFilter === 'all') return;
    if (!assignedCategoryOptions.includes(assignedCategoryFilter)) {
      setAssignedCategoryFilter('all');
    }
  }, [assignedCategoryFilter, assignedCategoryOptions]);

  const sequenceByItem = useMemo(() => {
    const start = Number.isFinite(sequenceStart) && sequenceStart > 0 ? Math.floor(sequenceStart) : 1;
    const map = new Map<string, number>();
    assignedItems.forEach((row, index) => {
      map.set(row.item, start + index);
    });
    return map;
  }, [assignedItems, sequenceStart]);

  const rebuildLists = (rows: SequenceSourceRow[], preserveCurrent = true, forceUnassignedAll = false) => {
    const filtered = includeOnlyTokenRows ? rows.filter((row) => row.tokenQuantity > 0) : rows;
    const uniqueItems = Array.from(new Set(filtered.map((row) => row.requestedItem.trim()).filter(Boolean)));

    const currentOrdered = preserveCurrent ? assignedItems.map((a) => a.item) : [];

    const historicalEntries = SEQUENCE_2025_DEFAULT.map((item, index) => ({
      item,
      normalized: normalizeItemName(item),
      tokenSet: tokenSet(item),
      seq: index + 1,
    }));

    const fallbackOrderMap = new Map<string, number>();

    uniqueItems.forEach((item) => {
      const normalized = normalizeItemName(item);
      const exact = sequence2025Map.get(normalized);
      if (exact && exact > 0) {
        fallbackOrderMap.set(item, exact);
        return;
      }

      const itemTokens = tokenSet(item);
      let bestSeq = 0;
      let bestScore = 0;
      historicalEntries.forEach((entry) => {
        let score = 0;
        if (entry.normalized.includes(normalized) || normalized.includes(entry.normalized)) {
          score = Math.max(score, 0.92);
        }
        const overlap = overlapScore(itemTokens, entry.tokenSet);
        if (overlap > score) score = overlap;
        if (score > bestScore) {
          bestScore = score;
          bestSeq = entry.seq;
        }
      });

      if (bestSeq > 0 && bestScore >= 0.45) {
        fallbackOrderMap.set(item, bestSeq);
      } else {
        fallbackOrderMap.set(item, Number.MAX_SAFE_INTEGER);
      }
    });

    const assigned: SequenceItem[] = [];
    if (!forceUnassignedAll) {
      const uniqueSet = new Set(uniqueItems);
      currentOrdered.forEach((item) => {
        if (uniqueSet.has(item)) assigned.push({ item });
      });
    }

    const assignedSet = new Set(assigned.map((a) => a.item));
    const unassigned = uniqueItems
      .filter((item) => !assignedSet.has(item))
      .sort((a, b) => {
        const aFallback = fallbackOrderMap.get(a) || Number.MAX_SAFE_INTEGER;
        const bFallback = fallbackOrderMap.get(b) || Number.MAX_SAFE_INTEGER;
        if (aFallback !== bFallback) return aFallback - bFallback;

        return a.localeCompare(b, undefined, { sensitivity: 'base' });
      });

    setAssignedItems(assigned);
    setUnassignedItems(unassigned);
    setSelectedLeft(new Set());
    setSelectedRight(new Set());
  };

  useEffect(() => {
    if (!sourceRows.length) return;
    rebuildLists(sourceRows, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [includeOnlyTokenRows]);

  const handleLoadFromDb = async () => {
    try {
      setIsLoadingDb(true);
      setSourceMode('db');
      const rows = await fetchSeatAllocationRows(DEFAULT_SESSION_NAME);
      if (!rows.length) {
        showWarning('No Seat Allocation rows found in DB.');
        setSourceRows([]);
        setAssignedItems([]);
        setUnassignedItems([]);
        return;
      }
      const mappedRows = rows.map(toDbSourceRow);
      setSourceRows(mappedRows);
      setSourceFileName(rows[0]?.source_file_name || 'seat_allocation_db');
      rebuildLists(mappedRows, false, true);
      showSuccess(`Loaded ${mappedRows.length} rows.`);
    } catch (error) {
      console.error('Failed to load sequence source from DB:', error);
      showError('Failed to load Seat Allocation rows from DB.');
    } finally {
      setIsLoadingDb(false);
    }
  };

  const handleUploadCsv = async (file: File) => {
    try {
      setIsLoadingCsv(true);
      setSourceMode('csv');
      const text = await file.text();
      const parsed = parseCSVRows(text);
      if (parsed.length < 2) {
        showError('CSV is empty or invalid.');
        return;
      }

      const headers = parsed[0].map((h) => h.trim());
      const itemHeader = findHeaderName(headers, ['Requested Item', 'Item', 'Article', 'Article Name', 'requested_item']);
      const tokenHeader = findHeaderName(headers, ['Token Quantity', 'Token Qty', 'token_quantity', 'Token']);

      if (!itemHeader) {
        showError('CSV missing item column. Expected Requested Item / Item / Article.');
        return;
      }

      const headerIndex = new Map(headers.map((h, i) => [h, i]));
      const csvRows: SequenceSourceRow[] = parsed
        .slice(1)
        .map((cells) => {
          const rowMap: Record<string, any> = {};
          headers.forEach((header, idx) => {
            rowMap[header] = cells[idx] ?? '';
          });
          const tokenQuantity = tokenHeader ? parseNumber(cells[headerIndex.get(tokenHeader) || 0]) : 0;
          const requestedItem = String(cells[headerIndex.get(itemHeader) || 0] || '').trim();
          return {
            requestedItem,
            tokenQuantity,
            rowMap,
            headers,
          };
        })
        .filter((row) => row.requestedItem);

      if (!csvRows.length) {
        showWarning('No usable rows found in CSV.');
        return;
      }

      setSourceRows(csvRows);
      setSourceFileName(file.name);
      rebuildLists(csvRows, false, true);
      showSuccess(`Loaded ${csvRows.length} rows from CSV.`);
    } catch (error) {
      console.error('Failed to parse CSV for sequence list:', error);
      showError('Failed to load CSV.');
    } finally {
      setIsLoadingCsv(false);
    }
  };

  const moveSelectedRight = () => {
    if (!selectedLeft.size) return;
    const moving = unassignedItems.filter((item) => selectedLeft.has(item));
    if (!moving.length) return;

    const additions = moving.map((item) => ({ item }));

    setAssignedItems((prev) => [...prev, ...additions]);
    setUnassignedItems((prev) => prev.filter((item) => !selectedLeft.has(item)));
    setSelectedLeft(new Set());
  };

  const moveSelectedLeft = () => {
    if (!selectedRight.size) return;
    const returning = assignedItems.filter((row) => selectedRight.has(row.item)).map((row) => row.item);
    if (!returning.length) return;

    setAssignedItems((prev) => prev.filter((row) => !selectedRight.has(row.item)));
    setUnassignedItems((prev) =>
      Array.from(new Set([...prev, ...returning])).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
    );
    setSelectedRight(new Set());
  };

  const handleSortAssignedByItem = () => {
    setAssignedItems((prev) =>
      [...prev].sort((a, b) => a.item.localeCompare(b.item, undefined, { sensitivity: 'base' }))
    );
  };

  const handleDropOnItem = (targetItem: string) => {
    if (!draggingItem || draggingItem === targetItem) return;
    setAssignedItems((prev) => {
      const sourceIndex = prev.findIndex((r) => r.item === draggingItem);
      const targetIndex = prev.findIndex((r) => r.item === targetItem);
      if (sourceIndex < 0 || targetIndex < 0) return prev;
      const next = [...prev];
      const [moved] = next.splice(sourceIndex, 1);
      next.splice(targetIndex, 0, moved);
      return next;
    });
    setDraggingItem(null);
  };

  const handleExport = () => {
    if (!sourceRows.length) {
      showWarning('Load DB rows or upload CSV first.');
      return;
    }
    if (unassignedItems.length > 0) {
      showWarning(`Still ${unassignedItems.length} unassigned item(s). Move all to sequenced list.`);
      return;
    }
    const allHeaders = sourceRows[0].headers;
    const exportHeaders = [...allHeaders, 'Sequence No'];

    const exportRows = sourceRows.map((row) => ({
      ...row.rowMap,
      'Sequence No': sequenceByItem.get(row.requestedItem) || '',
    }));

    exportToCSV(exportRows, 'sequence-list-appended', exportHeaders, showWarning);
    showSuccess('Sequence-appended CSV exported.');
  };

  const handleResetToSuggested = () => {
    if (!sourceRows.length) {
      showWarning('Load DB rows or upload CSV first.');
      return;
    }
    rebuildLists(sourceRows, false, true);
    showSuccess('Assigned list cleared. All items moved to unassigned.');
  };

  const handleSaveToDb = async () => {
    if (!sourceRows.length) {
      showWarning('Load DB rows first.');
      return;
    }
    if (sourceMode !== 'db') {
      showWarning('Save to DB works only for "Use Seat Allocation (DB)".');
      return;
    }
    const rowsToUpdate = sourceRows
      .filter((row) => row.sourceId)
      .map((row) => {
        const headers = Array.from(
          new Set([
            ...row.headers.filter((header) => normalizeHeader(header) !== 'sequence no'),
            'Sequence No',
          ])
        );
        return {
          id: row.sourceId as string,
          master_row: {
            ...row.rowMap,
            'Sequence No': sequenceByItem.get(row.requestedItem) || '',
          },
          master_headers: headers,
        };
      });

    if (!rowsToUpdate.length) {
      showWarning('No DB-linked rows found to save.');
      return;
    }

    try {
      setIsSavingDb(true);
      await updateSeatAllocationSequenceData(rowsToUpdate);
      showSuccess(`Saved sequence for ${rowsToUpdate.length} rows in DB.`);
    } catch (error) {
      console.error('Failed to save sequence to DB:', error);
      showError('Failed to save sequence data to DB.');
    } finally {
      setIsSavingDb(false);
    }
  };

  useEffect(() => {
    if (sourceMode !== 'db') return;
    if (!sourceRows.length) return;
    if (isLoadingDb || isSavingDb) return;

    const rowsToUpdate = sourceRows
      .filter((row) => row.sourceId)
      .map((row) => {
        const headers = Array.from(
          new Set([
            ...row.headers.filter((header) => normalizeHeader(header) !== 'sequence no'),
            'Sequence No',
          ])
        );
        return {
          id: row.sourceId as string,
          master_row: {
            ...row.rowMap,
            'Sequence No': sequenceByItem.get(row.requestedItem) || '',
          },
          master_headers: headers,
        };
      });

    if (!rowsToUpdate.length) return;

    const timer = window.setTimeout(async () => {
      try {
        setIsAutoSavingDb(true);
        await updateSeatAllocationSequenceData(rowsToUpdate);
      } catch (error) {
        console.error('Auto-save failed for sequence data:', error);
      } finally {
        setIsAutoSavingDb(false);
      }
    }, 700);

    return () => window.clearTimeout(timer);
  }, [assignedItems, sourceRows, sourceMode, isLoadingDb, isSavingDb]);

  return (
    <div className="p-3 sm:p-4">
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-3 sm:p-4 mb-3 shadow-sm">
        <div className="flex flex-col gap-3">
          <div className="border-b border-gray-200 dark:border-gray-700 pb-2">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
              <h1 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-white">Sequence List</h1>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={handleLoadFromDb}
                  disabled={isLoadingDb}
                  className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50"
                >
                  <RefreshCw className={`w-4 h-4 ${isLoadingDb ? 'animate-spin' : ''}`} />
                  Use Seat Allocation (DB)
                </button>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isLoadingCsv}
                  className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm disabled:opacity-50"
                >
                  <FileUp className="w-4 h-4" />
                  {isLoadingCsv ? 'Uploading...' : 'Upload Seat Allocation CSV'}
                </button>
                <button
                  type="button"
                  onClick={handleResetToSuggested}
                  disabled={!sourceRows.length}
                  className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-amber-300 text-amber-700 dark:text-amber-300 text-sm hover:bg-amber-50 dark:hover:bg-amber-900/30 disabled:opacity-50"
                >
                  <RotateCcw className="w-4 h-4" />
                  Reset (Clear Assigned)
                </button>
                <button
                  type="button"
                  onClick={handleExport}
                  disabled={!sourceRows.length}
                  className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-green-300 text-green-700 dark:text-green-300 text-sm hover:bg-green-50 dark:hover:bg-green-900/30 disabled:opacity-50"
                >
                  <Download className="w-4 h-4" />
                  Export Appended CSV
                </button>
                <button
                  type="button"
                  onClick={handleSaveToDb}
                  disabled={!sourceRows.length || sourceMode !== 'db' || isSavingDb}
                  className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-indigo-300 text-indigo-700 dark:text-indigo-300 text-sm hover:bg-indigo-50 dark:hover:bg-indigo-900/30 disabled:opacity-50"
                >
                  <Save className="w-4 h-4" />
                  {isSavingDb ? 'Saving...' : 'Save Now'}
                </button>
              </div>
            </div>
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void handleUploadCsv(file);
              e.currentTarget.value = '';
            }}
          />

          <div className="flex flex-wrap items-center gap-4 text-sm text-gray-600 dark:text-gray-300">
            <span>Source: <strong>{sourceMode === 'db' ? 'DB Seat Allocation' : 'Uploaded CSV'}</strong></span>
            <span>Rows: <strong>{dataRowCount}</strong></span>
            <span>Unique Items: <strong>{uniqueItemCount}</strong></span>
            <span>Sequenced: <strong>{assignedItems.length}</strong></span>
            <span>Unassigned: <strong>{unassignedItems.length}</strong></span>
            {sourceFileName ? <span>File: <strong>{sourceFileName}</strong></span> : null}
            {sourceMode === 'db' ? <span>Auto Save: <strong>{isAutoSavingDb ? 'Saving...' : 'On'}</strong></span> : null}
            <label className="inline-flex items-center gap-2">
              <span>Start From</span>
              <input
                type="number"
                min={1}
                step={1}
                value={sequenceStart}
                onChange={(e) => {
                  const parsed = Number(e.target.value);
                  setSequenceStart(Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : 1);
                }}
                className="w-24 px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
              />
            </label>
            <label className="inline-flex items-center gap-2">
              <input
                type="checkbox"
                checked={includeOnlyTokenRows}
                onChange={(e) => setIncludeOnlyTokenRows(e.target.checked)}
              />
              Include only Token Quantity {'>'} 0
            </label>
          </div>

        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_auto_1fr] gap-3">
        <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="px-3 py-2 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between gap-2">
            <div className="text-sm font-semibold text-gray-800 dark:text-gray-100">Unassigned Items</div>
            <div className="flex items-center gap-2 w-full max-w-md justify-end">
              <button
                type="button"
                onClick={() =>
                  setSelectedLeft((prev) => {
                    const next = new Set(prev);
                    filteredUnassignedItems.forEach((item) => next.add(item));
                    return next;
                  })
                }
                disabled={filteredUnassignedItems.length === 0}
                className="px-2 py-1 rounded border border-gray-300 dark:border-gray-600 text-xs hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50"
              >
                Select All
              </button>
              <button
                type="button"
                onClick={() => setSelectedLeft(new Set())}
                disabled={selectedLeft.size === 0}
                className="px-2 py-1 rounded border border-gray-300 dark:border-gray-600 text-xs hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50"
              >
                Deselect All
              </button>
              <select
                value={unassignedCategoryFilter}
                onChange={(e) => setUnassignedCategoryFilter(e.target.value)}
                className="w-40 px-2 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
              >
                <option value="all">All Categories</option>
                {unassignedCategoryOptions.map((category) => (
                  <option key={category} value={category}>
                    {category}
                  </option>
                ))}
              </select>
              <div className="relative w-52 max-w-full">
                <input
                  type="text"
                  value={unassignedSearch}
                  onChange={(e) => setUnassignedSearch(e.target.value)}
                  placeholder="Search items..."
                  className="w-full px-2.5 py-1 pr-7 text-xs rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                />
                {unassignedSearch && (
                  <button
                    type="button"
                    onClick={() => setUnassignedSearch('')}
                    className="absolute right-1 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100 text-xs px-1"
                    aria-label="Clear search"
                    title="Clear search"
                  >
                    ×
                  </button>
                )}
              </div>
            </div>
          </div>
          <div className="max-h-[65vh] overflow-auto p-2">
            {filteredUnassignedItems.length === 0 ? (
              <div className="text-sm text-gray-500 dark:text-gray-400 p-2">No unassigned items.</div>
            ) : (
              <div className="space-y-1">
                {filteredUnassignedItems.map((item) => (
                  <label key={item} className="flex items-center gap-2 p-2 rounded hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedLeft.has(item)}
                      onChange={(e) => {
                        setSelectedLeft((prev) => {
                          const next = new Set(prev);
                          if (e.target.checked) next.add(item);
                          else next.delete(item);
                          return next;
                        });
                      }}
                    />
                    <span className="text-sm text-gray-900 dark:text-white">{item}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="flex lg:flex-col items-center justify-center gap-2">
          <button
            type="button"
            onClick={moveSelectedRight}
            disabled={selectedLeft.size === 0}
            className="px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 text-sm hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50"
          >
            &gt;
          </button>
          <button
            type="button"
            onClick={moveSelectedLeft}
            disabled={selectedRight.size === 0}
            className="px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 text-sm hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50"
          >
            &lt;
          </button>
        </div>

        <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="px-3 py-2 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between gap-2">
            <div className="text-sm font-semibold text-gray-800 dark:text-gray-100">Sequenced Items</div>
            <div className="flex items-center gap-2">
              <select
                value={assignedCategoryFilter}
                onChange={(e) => setAssignedCategoryFilter(e.target.value)}
                className="w-40 px-2 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
              >
                <option value="all">All Categories</option>
                {assignedCategoryOptions.map((category) => (
                  <option key={category} value={category}>
                    {category}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => setSelectedRight(new Set(filteredAssignedItems.map((row) => row.item)))}
                disabled={filteredAssignedItems.length === 0}
                className="px-2 py-1 rounded border border-gray-300 dark:border-gray-600 text-xs hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50"
              >
                Select All
              </button>
              <button
                type="button"
                onClick={handleSortAssignedByItem}
                disabled={assignedItems.length === 0}
                className="px-2 py-1 rounded border border-gray-300 dark:border-gray-600 text-xs hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50"
              >
                Sort by Item
              </button>
            </div>
          </div>
          <div className="max-h-[65vh] overflow-auto p-2">
            {filteredAssignedItems.length === 0 ? (
              <div className="text-sm text-gray-500 dark:text-gray-400 p-2">No sequenced items yet.</div>
            ) : (
              <div className="space-y-1">
                {filteredAssignedItems.map((row) => (
                  <div
                    key={row.item}
                    draggable
                    onDragStart={() => setDraggingItem(row.item)}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={() => handleDropOnItem(row.item)}
                    onDragEnd={() => setDraggingItem(null)}
                    className="flex items-center gap-2 p-2 rounded hover:bg-gray-50 dark:hover:bg-gray-800 cursor-move"
                  >
                    <input
                      type="checkbox"
                      checked={selectedRight.has(row.item)}
                      onChange={(e) => {
                        setSelectedRight((prev) => {
                          const next = new Set(prev);
                          if (e.target.checked) next.add(row.item);
                          else next.delete(row.item);
                          return next;
                        });
                      }}
                    />
                    <span className="w-12 text-xs text-gray-500 dark:text-gray-400 text-right">
                      {sequenceByItem.get(row.item) || ''}
                    </span>
                    <span className="text-sm text-gray-900 dark:text-white">{row.item}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Phase2SequenceList;
