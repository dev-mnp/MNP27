import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Download, FileUp, Minus, Plus, RefreshCw, Save, Search, Upload } from 'lucide-react';
import { exportToCSV } from '../utils/csvExport';
import { useNotifications } from '../contexts/NotificationContext';
import {
  fetchSeatAllocationRows,
  replaceSeatAllocationSessionRows,
  type SeatAllocationRow,
  type SeatAllocationUploadRow,
  updateSeatAllocationRowQuantities,
} from '../services/seatAllocationService';

type InputRecord = {
  applicationNumber: string;
  beneficiaryName: string;
  requestedItem: string;
  quantity: number;
  beneficiaryType: string;
  itemType: string;
  comments: string;
};

type SplitRow = InputRecord & {
  id: string;
  district: string;
  waitingHallQuantity: number;
  tokenQuantity: number;
  masterRow: Record<string, any>;
  masterHeaders: string[];
};

const DEFAULT_SESSION_NAME = 'default';

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

const sanitizeNumber = (value: string): number => {
  const cleaned = value.replace(/,/g, '').trim();
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : 0;
};

const getDistrictFromRecord = (row: InputRecord): string => {
  if (row.beneficiaryType.toLowerCase() === 'district') return row.beneficiaryName;
  return 'Non-District';
};

const mapDbRowToUi = (row: SeatAllocationRow): SplitRow => ({
  id: row.id,
  applicationNumber: row.application_number || '',
  beneficiaryName: row.beneficiary_name || '',
  district: row.district || '',
  requestedItem: row.requested_item || '',
  quantity: Number(row.quantity) || 0,
  waitingHallQuantity: Number(row.waiting_hall_quantity) || 0,
  tokenQuantity: Number(row.token_quantity) || 0,
  beneficiaryType: row.beneficiary_type || '',
  itemType: row.item_type || '',
  comments: row.comments || '',
  masterRow: (row.master_row as Record<string, any>) || {},
  masterHeaders: (row.master_headers as string[]) || [],
});

const toUploadRow = (row: SplitRow): SeatAllocationUploadRow => ({
  application_number: row.applicationNumber,
  beneficiary_name: row.beneficiaryName,
  district: row.district,
  requested_item: row.requestedItem,
  quantity: row.quantity,
  waiting_hall_quantity: row.waitingHallQuantity,
  token_quantity: row.tokenQuantity,
  beneficiary_type: row.beneficiaryType,
  item_type: row.itemType,
  comments: row.comments,
  master_row: row.masterRow || {},
  master_headers: row.masterHeaders || [],
});

const sortRowsByDistrictAndArticle = (rows: SplitRow[]): SplitRow[] =>
  [...rows].sort((a, b) => {
    const districtCompare = a.district.localeCompare(b.district, undefined, { sensitivity: 'base' });
    if (districtCompare !== 0) return districtCompare;
    const articleCompare = a.requestedItem.localeCompare(b.requestedItem, undefined, { sensitivity: 'base' });
    if (articleCompare !== 0) return articleCompare;
    return a.applicationNumber.localeCompare(b.applicationNumber, undefined, { sensitivity: 'base' });
  });

const parseNumeric = (value: unknown): number => {
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0;
  if (typeof value === 'string') {
    const cleaned = value.replace(/,/g, '').trim();
    const parsed = Number(cleaned);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
};

const normalizeBeneficiaryType = (value: string): string =>
  String(value || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, ' ');

const isInstitutionType = (value: string): boolean => {
  const normalized = normalizeBeneficiaryType(value);
  return normalized === 'institution' || normalized === 'institutions' || normalized === 'instn';
};

const mergeMasterRowValues = (
  existingMasterRow: Record<string, any>,
  incomingMasterRow: Record<string, any>,
  mergedQuantity: number
): Record<string, any> => {
  const merged = { ...existingMasterRow };

  const existingTotalValue =
    parseNumeric(existingMasterRow['Total Value']) ||
    parseNumeric(existingMasterRow['TOTAL COST']) ||
    parseNumeric(existingMasterRow['TOTAL VALUE']) ||
    parseNumeric(existingMasterRow['Total Amount']) ||
    parseNumeric(existingMasterRow['total_value']) ||
    parseNumeric(existingMasterRow['total_amount']);

  const incomingTotalValue =
    parseNumeric(incomingMasterRow['Total Value']) ||
    parseNumeric(incomingMasterRow['TOTAL COST']) ||
    parseNumeric(incomingMasterRow['TOTAL VALUE']) ||
    parseNumeric(incomingMasterRow['Total Amount']) ||
    parseNumeric(incomingMasterRow['total_value']) ||
    parseNumeric(incomingMasterRow['total_amount']);

  const mergedTotalValue = existingTotalValue + incomingTotalValue;

  // Keep source header order metadata if present.
  if (!merged.__header_order && incomingMasterRow.__header_order) {
    merged.__header_order = incomingMasterRow.__header_order;
  }

  // Sync quantity in common key variants.
  const quantityKeys = ['Quantity', 'QUANTITY', 'quantity'];
  quantityKeys.forEach((key) => {
    if (key in existingMasterRow || key in incomingMasterRow) {
      merged[key] = mergedQuantity;
    }
  });

  // Sync total value in common key variants.
  const totalValueKeys = ['Total Value', 'TOTAL COST', 'TOTAL VALUE', 'Total Amount', 'total_value', 'total_amount'];
  totalValueKeys.forEach((key) => {
    if (key in existingMasterRow || key in incomingMasterRow) {
      merged[key] = mergedTotalValue;
    }
  });

  // Sync cost/unit where available using merged total and merged quantity.
  const mergedCostPerUnit = mergedQuantity > 0 ? mergedTotalValue / mergedQuantity : 0;
  const costPerUnitKeys = ['Cost Per Unit', 'COST PER UNIT', 'cost_per_unit'];
  costPerUnitKeys.forEach((key) => {
    if (key in existingMasterRow || key in incomingMasterRow) {
      merged[key] = mergedCostPerUnit;
    }
  });

  return merged;
};

const auditMergedRowIntegrity = (
  beforeRow: Record<string, any>,
  afterRow: Record<string, any>
): string[] => {
  const allowedToChange = new Set([
    'Quantity',
    'QUANTITY',
    'quantity',
    'Total Value',
    'TOTAL COST',
    'TOTAL VALUE',
    'Total Amount',
    'total_value',
    'total_amount',
    'Cost Per Unit',
    'COST PER UNIT',
    'cost_per_unit',
    '__header_order',
  ]);

  const keys = new Set([...Object.keys(beforeRow || {}), ...Object.keys(afterRow || {})]);
  const unexpectedChanges: string[] = [];

  keys.forEach((key) => {
    if (allowedToChange.has(key)) return;
    const beforeVal = beforeRow?.[key];
    const afterVal = afterRow?.[key];
    if (JSON.stringify(beforeVal) !== JSON.stringify(afterVal)) {
      unexpectedChanges.push(key);
    }
  });

  return unexpectedChanges;
};

type MergedAuditRow = {
  'Application Number': string;
  District: string;
  'Requested Item': string;
  'Beneficiary Name': string;
  'Merged Rows Count': number;
  'Quantity Before': number;
  'Quantity Added': number;
  'Quantity After': number;
  'Total Value Before': number;
  'Total Value Added': number;
  'Total Value After': number;
};

const extractRowTotalValue = (masterRow: Record<string, any>): number => {
  return (
    parseNumeric(masterRow['Total Value']) ||
    parseNumeric(masterRow['TOTAL COST']) ||
    parseNumeric(masterRow['TOTAL VALUE']) ||
    parseNumeric(masterRow['Total Amount']) ||
    parseNumeric(masterRow['total_value']) ||
    parseNumeric(masterRow['total_amount'])
  );
};

const dedupeUploadRows = (rows: SeatAllocationUploadRow[]): {
  dedupedRows: SeatAllocationUploadRow[];
  mergedAuditRows: MergedAuditRow[];
} => {
  const map = new Map<string, SeatAllocationUploadRow>();
  const mergedAuditByKey = new Map<string, MergedAuditRow>();

  rows.forEach((row, index) => {
    const key = [
      row.application_number.trim(),
      row.district.trim(),
      row.requested_item.trim(),
      row.beneficiary_name.trim(),
    ].join('||');

    const existing = map.get(key);
    if (!existing) {
      map.set(key, {
        ...row,
        sort_order: index + 1,
      });
      return;
    }

    const existingMasterRow = (existing.master_row || {}) as Record<string, any>;
    const incomingMasterRow = (row.master_row || {}) as Record<string, any>;
    const existingQuantity = existing.quantity || 0;
    const incomingQuantity = row.quantity || 0;
    const mergedQuantity = (existing.quantity || 0) + (row.quantity || 0);
    const mergedMasterRow = mergeMasterRowValues(
      existingMasterRow,
      incomingMasterRow,
      mergedQuantity
    );
    const unexpectedChanges = auditMergedRowIntegrity(existingMasterRow, mergedMasterRow);
    if (unexpectedChanges.length > 0) {
      throw new Error(
        `Merge audit failed. Unexpected master column change(s): ${unexpectedChanges.join(', ')}`
      );
    }

    const existingTotalValue = extractRowTotalValue(existingMasterRow);
    const incomingTotalValue = extractRowTotalValue(incomingMasterRow);
    const mergedTotalValue = extractRowTotalValue(mergedMasterRow);

    const currentAudit = mergedAuditByKey.get(key);
    if (!currentAudit) {
      mergedAuditByKey.set(key, {
        'Application Number': row.application_number,
        District: row.district,
        'Requested Item': row.requested_item,
        'Beneficiary Name': row.beneficiary_name,
        'Merged Rows Count': 2,
        'Quantity Before': existingQuantity,
        'Quantity Added': incomingQuantity,
        'Quantity After': mergedQuantity,
        'Total Value Before': existingTotalValue,
        'Total Value Added': incomingTotalValue,
        'Total Value After': mergedTotalValue,
      });
    } else {
      currentAudit['Merged Rows Count'] += 1;
      currentAudit['Quantity Added'] += incomingQuantity;
      currentAudit['Quantity After'] = currentAudit['Quantity Before'] + currentAudit['Quantity Added'];
      currentAudit['Total Value Added'] += incomingTotalValue;
      currentAudit['Total Value After'] = currentAudit['Total Value Before'] + currentAudit['Total Value Added'];
      mergedAuditByKey.set(key, currentAudit);
    }

    map.set(key, {
      ...existing,
      quantity: mergedQuantity,
      waiting_hall_quantity: 0,
      token_quantity: mergedQuantity,
      comments: [existing.comments, row.comments].filter(Boolean).join(' | ').slice(0, 2000),
      master_row: mergedMasterRow,
      master_headers: existing.master_headers || row.master_headers || [],
    });
  });

  return {
    dedupedRows: Array.from(map.values()),
    mergedAuditRows: Array.from(mergedAuditByKey.values()),
  };
};

const Phase2HallStageSplit: React.FC = () => {
  const { showError, showSuccess, showWarning } = useNotifications();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const debounceTimersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const [allRows, setAllRows] = useState<SplitRow[]>([]);
  const [fileName, setFileName] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [districtFilter, setDistrictFilter] = useState('all');
  const [articleFilter, setArticleFilter] = useState('all');
  const [beneficiaryTypeFilter, setBeneficiaryTypeFilter] = useState('district');
  const [sortColumn, setSortColumn] = useState<
    'district' | 'applicationNumber' | 'beneficiaryName' | 'requestedItem' | 'quantity' | 'waitingHallQuantity' | 'tokenQuantity' | null
  >(null);
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [isLoading, setIsLoading] = useState(false);
  const [isSavingUpload, setIsSavingUpload] = useState(false);
  const [isSavingNow, setIsSavingNow] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [mergedAuditRows, setMergedAuditRows] = useState<MergedAuditRow[]>([]);

  const normalizedType = normalizeBeneficiaryType(beneficiaryTypeFilter);
  const isDistrictType = normalizedType === 'district';
  const isInstitutionLikeType = normalizedType === 'institutions' || normalizedType === 'others';
  const isPublicType = normalizedType === 'public';
  const isPrimaryFilterEnabled = isDistrictType || isInstitutionLikeType;

  const districtOptions = useMemo(() => {
    const typeScopedRows = allRows.filter((row) => {
      const rowType = normalizeBeneficiaryType(row.beneficiaryType);
      if (isDistrictType) return rowType === 'district';
      if (normalizedType === 'institutions') return isInstitutionType(rowType);
      if (isInstitutionLikeType) return rowType === normalizedType;
      return false;
    });

    const articleScopedRows =
      articleFilter !== 'all'
        ? typeScopedRows.filter((row) => row.requestedItem === articleFilter)
        : typeScopedRows;

    const values = isDistrictType
      ? articleScopedRows.map((row) => row.district)
      : articleScopedRows.map((row) => row.beneficiaryName);

    return Array.from(new Set(values)).sort((a, b) =>
      a.localeCompare(b, undefined, { sensitivity: 'base' })
    );
  }, [allRows, articleFilter, isDistrictType, isInstitutionLikeType, normalizedType]);

  const articleOptions = useMemo(() => {
    const baseRows = allRows.filter((row) => {
      if (beneficiaryTypeFilter === 'all') return true;
      const rowType = normalizeBeneficiaryType(row.beneficiaryType);
      if (normalizedType === 'institutions') return isInstitutionType(rowType);
      return rowType === normalizedType;
    });

    const scopedRows = baseRows.filter((row) => {
      if (!isPrimaryFilterEnabled || districtFilter === 'all') return true;
      return isDistrictType ? row.district === districtFilter : row.beneficiaryName === districtFilter;
    });

    return Array.from(new Set(scopedRows.map((row) => row.requestedItem))).sort((a, b) =>
      a.localeCompare(b, undefined, { sensitivity: 'base' })
    );
  }, [allRows, beneficiaryTypeFilter, districtFilter, normalizedType, isPrimaryFilterEnabled, isDistrictType]);

  const visibleRows = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return allRows.filter((row) => {
      const rowType = normalizeBeneficiaryType(row.beneficiaryType);
      const matchesType =
        beneficiaryTypeFilter === 'all'
          ? true
          : normalizedType === 'institutions'
            ? isInstitutionType(rowType)
            : rowType === normalizedType;
      if (!matchesType) return false;
      if (isPrimaryFilterEnabled && districtFilter !== 'all') {
        if (isDistrictType && row.district !== districtFilter) return false;
        if (isInstitutionLikeType && row.beneficiaryName !== districtFilter) return false;
      }
      if (articleFilter !== 'all' && row.requestedItem !== articleFilter) return false;
      if (!query) return true;
      return (
        row.applicationNumber.toLowerCase().includes(query) ||
        row.beneficiaryName.toLowerCase().includes(query) ||
        row.requestedItem.toLowerCase().includes(query) ||
        row.comments.toLowerCase().includes(query)
      );
    });
  }, [allRows, articleFilter, beneficiaryTypeFilter, districtFilter, searchQuery, isPrimaryFilterEnabled, isDistrictType, isInstitutionLikeType]);

  const sortedVisibleRows = useMemo(() => {
    if (!sortColumn) return visibleRows;

    const rows = [...visibleRows];
    rows.sort((a, b) => {
      const getValue = (row: SplitRow) => {
        switch (sortColumn) {
          case 'district':
            return row.district || '';
          case 'applicationNumber':
            return row.applicationNumber || '';
          case 'beneficiaryName':
            return row.beneficiaryName || '';
          case 'requestedItem':
            return row.requestedItem || '';
          case 'quantity':
            return row.quantity || 0;
          case 'waitingHallQuantity':
            return row.waitingHallQuantity || 0;
          case 'tokenQuantity':
            return row.tokenQuantity || 0;
          default:
            return '';
        }
      };

      const aValue = getValue(a);
      const bValue = getValue(b);
      if (typeof aValue === 'string' && typeof bValue === 'string') {
        return sortDirection === 'asc'
          ? aValue.localeCompare(bValue, undefined, { sensitivity: 'base' })
          : bValue.localeCompare(aValue, undefined, { sensitivity: 'base' });
      }
      return sortDirection === 'asc'
        ? Number(aValue) - Number(bValue)
        : Number(bValue) - Number(aValue);
    });
    return rows;
  }, [visibleRows, sortColumn, sortDirection]);

  const totals = useMemo(
    () =>
      sortedVisibleRows.reduce(
        (acc, row) => {
          acc.quantity += row.quantity;
          acc.waitingHallQuantity += row.waitingHallQuantity;
          acc.tokenQuantity += row.tokenQuantity;
          return acc;
        },
        { quantity: 0, waitingHallQuantity: 0, tokenQuantity: 0 }
      ),
    [sortedVisibleRows]
  );

  const overallTotals = useMemo(
    () =>
      allRows.reduce(
        (acc, row) => {
          acc.quantity += row.quantity;
          acc.waitingHallQuantity += row.waitingHallQuantity;
          acc.tokenQuantity += row.tokenQuantity;
          return acc;
        },
        { quantity: 0, waitingHallQuantity: 0, tokenQuantity: 0 }
      ),
    [allRows]
  );

  const handleSort = (
    column: 'district' | 'applicationNumber' | 'beneficiaryName' | 'requestedItem' | 'quantity' | 'waitingHallQuantity' | 'tokenQuantity'
  ) => {
    if (sortColumn === column) {
      setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setSortColumn(column);
    setSortDirection('asc');
  };

  const getSortIcon = (
    column: 'district' | 'applicationNumber' | 'beneficiaryName' | 'requestedItem' | 'quantity' | 'waitingHallQuantity' | 'tokenQuantity'
  ) => {
    if (sortColumn === column) return sortDirection === 'asc' ? '↑' : '↓';
    return '⇅';
  };

  useEffect(() => {
    loadRows();
  }, []);

  useEffect(() => {
    if (!isPrimaryFilterEnabled && districtFilter !== 'all') {
      setDistrictFilter('all');
    }
  }, [isPrimaryFilterEnabled, districtFilter]);

  useEffect(() => {
    if (articleFilter !== 'all' && !articleOptions.includes(articleFilter)) {
      setArticleFilter('all');
    }
  }, [articleFilter, articleOptions]);

  useEffect(() => {
    return () => {
      Object.values(debounceTimersRef.current).forEach((timer) => clearTimeout(timer));
    };
  }, []);

  const loadRows = async () => {
    try {
      setIsLoading(true);
      const rows = await fetchSeatAllocationRows(DEFAULT_SESSION_NAME);
      setAllRows(sortRowsByDistrictAndArticle(rows.map(mapDbRowToUi)));
      setFileName(rows[0]?.source_file_name || '');
    } catch (error) {
      console.error('Failed to load seat allocation rows:', error);
      showError('Failed to load Seat Allocation data.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleUploadCSV = async (file: File) => {
    try {
      const text = await file.text();
      const parsedRows = parseCSVRows(text);
      if (parsedRows.length < 2) {
        showError('CSV is empty or invalid.');
        return;
      }

      const headers = parsedRows[0].map((header) => header.trim());
      const headerIndex = new Map<string, number>();
      headers.forEach((header, idx) => headerIndex.set(header.toLowerCase(), idx));

      const requiredHeaders = [
        'application number',
        'beneficiary name',
        'requested item',
        'quantity',
        'beneficiary type',
        'item type',
        'comments',
      ];

      const missing = requiredHeaders.filter((header) => !headerIndex.has(header));
      if (missing.length > 0) {
        showError(`Missing required column(s): ${missing.join(', ')}`);
        return;
      }

      const uploadRowsRaw: SeatAllocationUploadRow[] = parsedRows
        .slice(1)
        .map((row, index) => {
          const input: InputRecord = {
            applicationNumber: row[headerIndex.get('application number') || 0] || '',
            beneficiaryName: row[headerIndex.get('beneficiary name') || 0] || '',
            requestedItem: row[headerIndex.get('requested item') || 0] || '',
            quantity: sanitizeNumber(row[headerIndex.get('quantity') || 0] || '0'),
            beneficiaryType: row[headerIndex.get('beneficiary type') || 0] || '',
            itemType: row[headerIndex.get('item type') || 0] || '',
            comments: row[headerIndex.get('comments') || 0] || '',
          };
          const district = getDistrictFromRecord(input);
          const waitingHall = 0;
          const masterRow = headers.reduce((acc, header, headerIdx) => {
            acc[header] = row[headerIdx] ?? '';
            return acc;
          }, {} as Record<string, any>);
          return {
            application_number: input.applicationNumber,
            beneficiary_name: input.beneficiaryName,
            district,
            requested_item: input.requestedItem,
            quantity: input.quantity,
            waiting_hall_quantity: waitingHall,
            token_quantity: Math.max(0, input.quantity - waitingHall),
            beneficiary_type: input.beneficiaryType,
            item_type: input.itemType,
            comments: input.comments,
            master_row: masterRow,
            master_headers: headers,
            sort_order: index + 1,
          };
        })
        .filter((record) => record.application_number || record.beneficiary_name || record.requested_item || record.quantity > 0);

      const { dedupedRows: uploadRows, mergedAuditRows: mergedRows } = dedupeUploadRows(uploadRowsRaw);
      if (uploadRows.length === 0) {
        showWarning('No usable rows found in CSV.');
        return;
      }

      setIsSavingUpload(true);
      const saved = await replaceSeatAllocationSessionRows(DEFAULT_SESSION_NAME, file.name, uploadRows);
      setAllRows(sortRowsByDistrictAndArticle(saved.map(mapDbRowToUi)));
      setMergedAuditRows(mergedRows);
      setFileName(file.name);
      const mergedCount = mergedRows.length;
      showSuccess(
        mergedCount > 0
          ? `Saved ${saved.length} row(s) (${mergedCount} merged key group(s)). Download merged audit CSV if needed.`
          : `Saved ${saved.length} row(s)`
      );
    } catch (error) {
      console.error('Seat allocation upload failed:', error);
      const message = error instanceof Error ? error.message : 'Failed to upload and save CSV.';
      showError(message);
    } finally {
      setIsSavingUpload(false);
    }
  };

  const persistRowQuantity = (rowId: string, waitingHallQty: number, tokenQty: number) => {
    if (debounceTimersRef.current[rowId]) {
      clearTimeout(debounceTimersRef.current[rowId]);
    }
    debounceTimersRef.current[rowId] = setTimeout(async () => {
      try {
        await updateSeatAllocationRowQuantities(rowId, waitingHallQty, tokenQty);
      } catch (error) {
        console.error('Failed to persist seat quantity change:', error);
        showError('Failed to save one row. Click refresh to reload latest data.');
      } finally {
        delete debounceTimersRef.current[rowId];
      }
    }, 400);
  };

  const handleSaveNow = async () => {
    if (allRows.length === 0) {
      showWarning('No rows to save.');
      return;
    }

    Object.values(debounceTimersRef.current).forEach((timer) => clearTimeout(timer));
    debounceTimersRef.current = {};

    try {
      setIsSavingNow(true);
      await Promise.all(
        allRows.map((row) =>
          updateSeatAllocationRowQuantities(row.id, row.waitingHallQuantity, row.tokenQuantity)
        )
      );
      showSuccess(`Saved ${allRows.length} row(s).`);
    } catch (error) {
      console.error('Save now failed:', error);
      showError('Failed to save one or more rows.');
    } finally {
      setIsSavingNow(false);
    }
  };

  const handleWaitingQuantityChange = (rowId: string, rawValue: string) => {
    setAllRows((prev) =>
      prev.map((row) => {
        if (row.id !== rowId) return row;
        const waitingQty = Math.max(0, Math.floor(Number(rawValue) || 0));
        const boundedWaitingQty = Math.min(waitingQty, row.quantity);
        const nextTokenQty = row.quantity - boundedWaitingQty;
        persistRowQuantity(row.id, boundedWaitingQty, nextTokenQty);
        return {
          ...row,
          waitingHallQuantity: boundedWaitingQty,
          tokenQuantity: nextTokenQty,
        };
      })
    );
  };

  const handleWaitingQuantityStep = (rowId: string, delta: number) => {
    setAllRows((prev) =>
      prev.map((row) => {
        if (row.id !== rowId) return row;
        const nextWaiting = Math.max(0, Math.min(row.quantity, row.waitingHallQuantity + delta));
        const nextToken = row.quantity - nextWaiting;
        persistRowQuantity(row.id, nextWaiting, nextToken);
        return {
          ...row,
          waitingHallQuantity: nextWaiting,
          tokenQuantity: nextToken,
        };
      })
    );
  };

  const handleTokenQuantityStep = (rowId: string, delta: number) => {
    setAllRows((prev) =>
      prev.map((row) => {
        if (row.id !== rowId) return row;
        const nextToken = Math.max(0, Math.min(row.quantity, row.tokenQuantity + delta));
        const nextWaiting = row.quantity - nextToken;
        persistRowQuantity(row.id, nextWaiting, nextToken);
        return {
          ...row,
          waitingHallQuantity: nextWaiting,
          tokenQuantity: nextToken,
        };
      })
    );
  };

  const applyBulkWaitingHall = async (mode: 'full' | 'zero') => {
    if (sortedVisibleRows.length === 0) {
      showWarning('No filtered rows to update.');
      return;
    }

    const targetMap = new Map<string, { waiting: number; token: number }>();
    sortedVisibleRows.forEach((row) => {
      const waiting = mode === 'full' ? row.quantity : 0;
      const token = row.quantity - waiting;
      targetMap.set(row.id, { waiting, token });
    });

    setAllRows((prev) =>
      prev.map((row) => {
        const target = targetMap.get(row.id);
        if (!target) return row;
        return {
          ...row,
          waitingHallQuantity: target.waiting,
          tokenQuantity: target.token,
        };
      })
    );

    try {
      await Promise.all(
        Array.from(targetMap.entries()).map(([id, values]) =>
          updateSeatAllocationRowQuantities(id, values.waiting, values.token)
        )
      );
      showSuccess(
        mode === 'full'
          ? `Updated ${targetMap.size} filtered row(s): Waiting Hall = full quantity`
          : `Updated ${targetMap.size} filtered row(s): Waiting Hall = 0`
      );
    } catch (error) {
      console.error('Bulk seat allocation update failed:', error);
      showError('Bulk update failed for one or more rows. Click refresh and retry.');
    }
  };

  const handleReset = async () => {
    if (allRows.length === 0) {
      showWarning('No data available to reset.');
      return;
    }
    try {
      setIsResetting(true);
      const resetRows = allRows.map((row) => ({
        ...toUploadRow(row),
        waiting_hall_quantity: 0,
        token_quantity: row.quantity,
      }));
      const saved = await replaceSeatAllocationSessionRows(DEFAULT_SESSION_NAME, fileName || '', resetRows);
      setAllRows(sortRowsByDistrictAndArticle(saved.map(mapDbRowToUi)));
      showSuccess('All split values reset and saved.');
    } catch (error) {
      console.error('Failed to reset seat allocation rows:', error);
      showError('Failed to reset split values.');
    } finally {
      setIsResetting(false);
    }
  };

  const handleExport = () => {
    if (allRows.length === 0) {
      showWarning('No data to export.');
      return;
    }
    const sortedRows = sortRowsByDistrictAndArticle(allRows);
    const headerSourceRow = sortedRows.find((row) => (row.masterHeaders || []).length > 0);
    const orderedMasterHeaders =
      headerSourceRow?.masterHeaders ||
      Object.keys(sortedRows[0]?.masterRow || {});

    const filteredMasterHeaders = orderedMasterHeaders.filter(
      (h) => h.toLowerCase() !== 'waiting hall quantity' && h.toLowerCase() !== 'token quantity'
    );

    const exportHeaders = [...filteredMasterHeaders, 'Waiting Hall Quantity', 'Token Quantity'];

    const exportRows = sortedRows.map((row) => {
      const base = {} as Record<string, any>;
      filteredMasterHeaders.forEach((header) => {
        base[header] = row.masterRow?.[header] ?? '';
      });
      base['Waiting Hall Quantity'] = row.waitingHallQuantity;
      base['Token Quantity'] = row.tokenQuantity;
      return base;
    });
    exportToCSV(
      exportRows,
      'seat-allocation',
      exportHeaders,
      showWarning
    );
    showSuccess('Seat allocation exported successfully.');
  };

  const handleExportMergedAudit = () => {
    if (mergedAuditRows.length === 0) {
      showWarning('No merged rows in last upload.');
      return;
    }
    exportToCSV(
      mergedAuditRows,
      'seat-allocation-merged-audit',
      [
        'Application Number',
        'District',
        'Requested Item',
        'Beneficiary Name',
        'Merged Rows Count',
        'Quantity Before',
        'Quantity Added',
        'Quantity After',
        'Total Value Before',
        'Total Value Added',
        'Total Value After',
      ],
      showWarning
    );
    showSuccess('Merged rows audit CSV exported.');
  };

  return (
    <div className="p-3 sm:p-4">
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-3 sm:p-4 mb-3 shadow-sm">
        <div className="flex flex-col gap-3">
          <div className="border-b border-gray-200 dark:border-gray-700 pb-2">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
              <h1 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-white">Seat Allocation</h1>
              <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isSavingUpload || isLoading}
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm disabled:opacity-50"
              >
                <FileUp className="w-4 h-4" />
                {isSavingUpload ? 'Uploading...' : 'Upload Master CSV'}
              </button>
              <button
                type="button"
                onClick={loadRows}
                disabled={isLoading}
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
              <button
                type="button"
                onClick={handleSaveNow}
                disabled={allRows.length === 0 || isSavingNow}
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-indigo-300 text-indigo-700 dark:text-indigo-300 text-sm hover:bg-indigo-50 dark:hover:bg-indigo-900/30 disabled:opacity-50"
              >
                <Save className="w-4 h-4" />
                {isSavingNow ? 'Saving...' : 'Save Now'}
              </button>
              <button
                type="button"
                onClick={handleReset}
                disabled={allRows.length === 0 || isResetting}
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${isResetting ? 'animate-spin' : ''}`} />
                Reset Splits
              </button>
              <button
                type="button"
                onClick={handleExport}
                disabled={allRows.length === 0}
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-green-300 text-green-700 dark:text-green-300 text-sm hover:bg-green-50 dark:hover:bg-green-900/30 disabled:opacity-50"
              >
                <Download className="w-4 h-4" />
                Export Split CSV
              </button>
              <button
                type="button"
                onClick={handleExportMergedAudit}
                disabled={mergedAuditRows.length === 0}
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-purple-300 text-purple-700 dark:text-purple-300 text-sm hover:bg-purple-50 dark:hover:bg-purple-900/30 disabled:opacity-50"
              >
                <Download className="w-4 h-4" />
                Export Merged Rows CSV
              </button>
              </div>
            </div>
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleUploadCSV(file);
              e.currentTarget.value = '';
            }}
            className="hidden"
          />

          <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-2.5 sm:p-3 bg-gray-50/60 dark:bg-gray-800/40">
            <div className="text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1.5">Filters</div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-2 sm:gap-3">
              <div className="relative lg:col-span-2">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search app no, district, beneficiary, item, comments..."
                className="w-full pl-9 pr-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white"
              />
              </div>
              <select
                value={beneficiaryTypeFilter}
                onChange={(e) => setBeneficiaryTypeFilter(e.target.value)}
                className="px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white"
              >
                <option value="district">District</option>
                <option value="public">Public</option>
                <option value="institutions">Institutions</option>
                <option value="others">Others</option>
                <option value="all">All Types</option>
              </select>
              <select
                value={districtFilter}
                onChange={(e) => setDistrictFilter(e.target.value)}
                disabled={!isPrimaryFilterEnabled}
                className="px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white disabled:opacity-60 disabled:cursor-not-allowed"
              >
                <option value="all">
                  {isDistrictType ? 'All Districts' : isInstitutionLikeType ? 'All Institutions' : isPublicType ? 'Public - N/A' : 'All'}
                </option>
                {districtOptions.map((district) => (
                  <option key={district} value={district}>
                    {district}
                  </option>
                ))}
              </select>
              <select
                value={articleFilter}
                onChange={(e) => setArticleFilter(e.target.value)}
                className="px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white"
              >
                <option value="all">All Items</option>
                {articleOptions.map((article) => (
                  <option key={article} value={article}>
                    {article}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-end gap-2 text-xs sm:text-sm">
            <div className="text-gray-600 dark:text-gray-400">
              Loaded: <span className="font-medium">{allRows.length}</span> row(s)
              {fileName ? <span> from <span className="font-medium">{fileName}</span></span> : null}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2">
            <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-2.5">
              <div className="text-[11px] text-gray-500 dark:text-gray-400">Quantity</div>
              <div className="text-base font-semibold text-gray-900 dark:text-white">{totals.quantity.toLocaleString('en-IN')}</div>
            </div>
            <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-2.5">
              <div className="text-[11px] text-gray-500 dark:text-gray-400">Waiting Hall Quantity</div>
              <div className="text-base font-semibold text-amber-600 dark:text-amber-400">{totals.waitingHallQuantity.toLocaleString('en-IN')}</div>
            </div>
            <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-2.5">
              <div className="text-[11px] text-gray-500 dark:text-gray-400">Token Quantity</div>
              <div className="text-base font-semibold text-green-600 dark:text-green-400">{totals.tokenQuantity.toLocaleString('en-IN')}</div>
            </div>
            <div className="rounded-lg border border-blue-200 dark:border-blue-700 p-2.5 bg-blue-50/30 dark:bg-blue-900/10">
              <div className="text-[11px] text-blue-700 dark:text-blue-300">All Beneficiaries Waiting Hall</div>
              <div className="text-base font-semibold text-blue-700 dark:text-blue-300">{overallTotals.waitingHallQuantity.toLocaleString('en-IN')}</div>
            </div>
            <div className="rounded-lg border border-emerald-200 dark:border-emerald-700 p-2.5 bg-emerald-50/30 dark:bg-emerald-900/10">
              <div className="text-[11px] text-emerald-700 dark:text-emerald-300">All Beneficiaries Token</div>
              <div className="text-base font-semibold text-emerald-700 dark:text-emerald-300">{overallTotals.tokenQuantity.toLocaleString('en-IN')}</div>
            </div>
          </div>

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => applyBulkWaitingHall('full')}
              disabled={sortedVisibleRows.length === 0}
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-blue-300 text-blue-700 dark:text-blue-300 text-sm hover:bg-blue-50 dark:hover:bg-blue-900/30 disabled:opacity-50"
            >
              Filtered: Waiting Hall Full
            </button>
            <button
              type="button"
              onClick={() => applyBulkWaitingHall('zero')}
              disabled={sortedVisibleRows.length === 0}
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-orange-300 text-orange-700 dark:text-orange-300 text-sm hover:bg-orange-50 dark:hover:bg-orange-900/30 disabled:opacity-50"
            >
              Filtered: Waiting Hall Empty
            </button>
          </div>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
        {sortedVisibleRows.length === 0 ? (
          <div className="p-10 text-center text-sm text-gray-500 dark:text-gray-400">
            {allRows.length === 0 ? (
              <div className="inline-flex items-center gap-2">
                <Upload className="w-4 h-4" />
                Upload exported master CSV to start.
              </div>
            ) : (
              'No rows match current filters.'
            )}
          </div>
        ) : (
          <div className="overflow-auto max-h-[75vh]">
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
                <tr>
                  <th
                    className="px-3 py-2 text-left font-medium text-gray-700 dark:text-gray-300 cursor-pointer select-none"
                    onClick={() => handleSort('district')}
                  >
                    District <span className="text-xs text-gray-400">{getSortIcon('district')}</span>
                  </th>
                  <th
                    className="px-3 py-2 text-left font-medium text-gray-700 dark:text-gray-300 cursor-pointer select-none"
                    onClick={() => handleSort('applicationNumber')}
                  >
                    App No <span className="text-xs text-gray-400">{getSortIcon('applicationNumber')}</span>
                  </th>
                  <th
                    className="px-3 py-2 text-left font-medium text-gray-700 dark:text-gray-300 cursor-pointer select-none"
                    onClick={() => handleSort('beneficiaryName')}
                  >
                    Beneficiary <span className="text-xs text-gray-400">{getSortIcon('beneficiaryName')}</span>
                  </th>
                  <th
                    className="px-3 py-2 text-left font-medium text-gray-700 dark:text-gray-300 cursor-pointer select-none"
                    onClick={() => handleSort('requestedItem')}
                  >
                    Item <span className="text-xs text-gray-400">{getSortIcon('requestedItem')}</span>
                  </th>
                  <th
                    className="px-3 py-2 text-right font-medium text-gray-700 dark:text-gray-300 cursor-pointer select-none"
                    onClick={() => handleSort('quantity')}
                  >
                    Quantity <span className="text-xs text-gray-400">{getSortIcon('quantity')}</span>
                  </th>
                  <th
                    className="px-3 py-2 text-right font-medium text-gray-700 dark:text-gray-300 cursor-pointer select-none"
                    onClick={() => handleSort('waitingHallQuantity')}
                  >
                    Waiting Hall <span className="text-xs text-gray-400">{getSortIcon('waitingHallQuantity')}</span>
                  </th>
                  <th
                    className="px-3 py-2 text-right font-medium text-gray-700 dark:text-gray-300 cursor-pointer select-none"
                    onClick={() => handleSort('tokenQuantity')}
                  >
                    Token <span className="text-xs text-gray-400">{getSortIcon('tokenQuantity')}</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {sortedVisibleRows.map((row) => (
                  <tr key={row.id}>
                    <td className="px-3 py-2 text-gray-900 dark:text-white">{row.district}</td>
                    <td className="px-3 py-2 text-gray-600 dark:text-gray-300">{row.applicationNumber}</td>
                    <td className="px-3 py-2 text-gray-900 dark:text-white">{row.beneficiaryName}</td>
                    <td className="px-3 py-2 text-gray-900 dark:text-white">{row.requestedItem}</td>
                    <td className="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{row.quantity}</td>
                    <td className="px-3 py-2">
                      <div className="ml-auto w-28 flex items-center justify-end gap-1">
                        <button
                          type="button"
                          onClick={() => handleWaitingQuantityStep(row.id, -1)}
                          disabled={row.waitingHallQuantity <= 0}
                          className="p-1 rounded border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700"
                          aria-label="Decrease waiting hall quantity"
                        >
                          <Minus className="w-3 h-3" />
                        </button>
                        <input
                          type="number"
                          min={0}
                          max={row.quantity}
                          step={1}
                          value={row.waitingHallQuantity}
                          onChange={(e) => handleWaitingQuantityChange(row.id, e.target.value)}
                          className="w-14 text-center px-1 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                        />
                        <button
                          type="button"
                          onClick={() => handleWaitingQuantityStep(row.id, 1)}
                          disabled={row.waitingHallQuantity >= row.quantity}
                          className="p-1 rounded border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700"
                          aria-label="Increase waiting hall quantity"
                        >
                          <Plus className="w-3 h-3" />
                        </button>
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <div className="ml-auto w-28 flex items-center justify-end gap-1">
                        <button
                          type="button"
                          onClick={() => handleTokenQuantityStep(row.id, -1)}
                          disabled={row.tokenQuantity <= 0}
                          className="p-1 rounded border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700"
                          aria-label="Decrease token quantity"
                        >
                          <Minus className="w-3 h-3" />
                        </button>
                        <div className="w-14 text-center px-1 py-1 rounded border border-transparent text-right font-medium text-green-700 dark:text-green-400">
                          {row.tokenQuantity}
                        </div>
                        <button
                          type="button"
                          onClick={() => handleTokenQuantityStep(row.id, 1)}
                          disabled={row.tokenQuantity >= row.quantity}
                          className="p-1 rounded border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700"
                          aria-label="Increase token quantity"
                        >
                          <Plus className="w-3 h-3" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default Phase2HallStageSplit;
