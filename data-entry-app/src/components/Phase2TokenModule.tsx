import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Download, FileUp, RefreshCw, Save } from 'lucide-react';
import ExcelJS from 'exceljs';
import { useNotifications } from '../contexts/NotificationContext';
import { fetchSeatAllocationRows, updateSeatAllocationSequenceData } from '../services/seatAllocationService';
import {
  buildNotebookTokenRows,
  downloadNotebookLabelsByType,
  type LabelLayout,
  type NotebookInputRow,
} from '../services/tokenLabelPdfService';
import { exportToCSV } from '../utils/csvExport';

const DEFAULT_SESSION_NAME = 'default';

type SourceMode = 'db' | 'csv';

type TokenRow = NotebookInputRow;

const normalizeHeader = (header: string) => header.trim().toLowerCase().replace(/\s+/g, ' ');
const normalizeText = (value: string) => value.trim().toLowerCase().replace(/\s+/g, ' ');
const isInstitutionType = (value: string) => {
  const normalized = normalizeText(value);
  return normalized === 'institution' || normalized === 'institutions' || normalized === 'instn';
};

const findHeaderName = (headers: string[], candidates: string[]): string | null => {
  const byNormalized = new Map(headers.map((h) => [normalizeHeader(h), h]));
  for (const candidate of candidates) {
    const found = byNormalized.get(normalizeHeader(candidate));
    if (found) return found;
  }
  return null;
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

const findObjectKey = (obj: Record<string, any>, candidates: string[]): string | null => {
  const byNormalized = new Map(Object.keys(obj).map((k) => [normalizeHeader(k), k]));
  for (const candidate of candidates) {
    const found = byNormalized.get(normalizeHeader(candidate));
    if (found) return found;
  }
  return null;
};

const parseAppAndName = (rawName: string): { appNo: string; name: string } => {
  const text = String(rawName || '').trim();
  if (text.includes(' - ')) {
    const [app, ...nameParts] = text.split(' - ');
    return { appNo: app.trim(), name: nameParts.join(' - ').trim() };
  }
  return { appNo: '', name: text };
};

const toLegacyBeneficiaryType = (type: string): string => {
  const normalized = normalizeText(type);
  if (isInstitutionType(normalized)) return 'Institution';
  if (normalized === 'district') return 'District';
  if (normalized === 'public') return 'Public';
  if (normalized === 'others') return 'Others';
  return type;
};

const DEFAULT_BIG_ITEMS = [
  'Steel Cupboard',
  'Office Table 4 X 2',
  'S Type Chair',
  'Reception 4 Seater',
  'Tiffen Set',
];

const Phase2TokenModule: React.FC = () => {
  const { showError, showSuccess, showWarning } = useNotifications();
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [sourceMode, setSourceMode] = useState<SourceMode>('db');
  const [isLoadingDb, setIsLoadingDb] = useState(false);
  const [isLoadingCsv, setIsLoadingCsv] = useState(false);
  const [isSavingDb, setIsSavingDb] = useState(false);
  const [isGeneratingLabels, setIsGeneratingLabels] = useState(false);
  const [sourceFileName, setSourceFileName] = useState('');
  const [rows, setRows] = useState<TokenRow[]>([]);
  const [publicAckRows, setPublicAckRows] = useState<Array<{
    id: string;
    applicationNumber: string;
    beneficiaryName: string;
    aadharNumber: string;
    item: string;
    waitingHallQuantity: number;
    district: string;
    tokenStartNo: number;
    tokenEndNo: number;
    mobile: string;
    address: string;
    notes: string;
  }>>([]);
  const [publicDetailsFileName, setPublicDetailsFileName] = useState('');
  const [isLoadingPublicDetails, setIsLoadingPublicDetails] = useState(false);
  const publicDetailsFileInputRef = useRef<HTMLInputElement | null>(null);
  const [startTokenNo, setStartTokenNo] = useState(1);
  const [bigItemsInput, setBigItemsInput] = useState(DEFAULT_BIG_ITEMS.join('\n'));
  const [printLayout, setPrintLayout] = useState<LabelLayout>('continuous');

  const bigItemSet = useMemo(
    () =>
      new Set(
        bigItemsInput
          .split('\n')
          .map((line) => normalizeText(line))
          .filter(Boolean)
      ),
    [bigItemsInput]
  );

  const generatedRows = useMemo(() => buildNotebookTokenRows(rows, startTokenNo, bigItemSet), [rows, startTokenNo, bigItemSet]);

  const usableRows = useMemo(
    () => generatedRows.filter((r) => r.tokenQuantity > 0 || r.waitingHallQuantity > 0),
    [generatedRows]
  );

  useEffect(() => {
    const next = generatedRows
      .filter((r) => normalizeText(r.beneficiaryType) === 'public' && r.waitingHallQuantity > 0)
      .map((row, index) => ({
        id: `${row.applicationNumber}-${row.requestedItem}-${index}`,
        applicationNumber: row.applicationNumber || parseAppAndName(row.beneficiaryName).appNo,
        beneficiaryName: parseAppAndName(row.beneficiaryName).name || row.beneficiaryName,
        aadharNumber: row.aadharNumber,
        item: row.requestedItem,
        waitingHallQuantity: row.waitingHallQuantity,
        district: row.district,
        tokenStartNo: row.startTokenNo,
        tokenEndNo: row.endTokenNo,
        mobile: '0',
        address: 'Add',
        notes: row.notes,
      }));
    setPublicAckRows(next);
  }, [generatedRows]);

  const updatePublicAckRow = (
    id: string,
    field:
      | 'beneficiaryName'
      | 'aadharNumber'
      | 'item'
      | 'waitingHallQuantity'
      | 'district'
      | 'mobile'
      | 'address'
      | 'notes',
    value: string
  ) => {
    setPublicAckRows((prev) =>
      prev.map((row) => {
        if (row.id !== id) return row;
        if (field === 'waitingHallQuantity') {
          return { ...row, waitingHallQuantity: Math.max(0, Math.floor(Number(value) || 0)) };
        }
        return { ...row, [field]: value };
      })
    );
  };

  const handleUploadPublicDetails = async (file: File) => {
    try {
      setIsLoadingPublicDetails(true);
      const rows: Record<string, any>[] = [];

      if (file.name.toLowerCase().endsWith('.csv')) {
        const text = await file.text();
        const parsed = parseCSVRows(text);
        if (parsed.length < 2) {
          showWarning('Public details CSV is empty.');
          return;
        }
        const headers = parsed[0].map((h) => String(h || '').trim());
        parsed.slice(1).forEach((cells) => {
          const row: Record<string, any> = {};
          headers.forEach((header, idx) => {
            row[header] = cells[idx] ?? '';
          });
          rows.push(row);
        });
      } else if (file.name.toLowerCase().endsWith('.xlsx') || file.name.toLowerCase().endsWith('.xls')) {
        const workbook = new ExcelJS.Workbook();
        const buffer = await file.arrayBuffer();
        await workbook.xlsx.load(buffer);
        const ws = workbook.worksheets[0];
        if (!ws || ws.rowCount < 2) {
          showWarning('Public details Excel is empty.');
          return;
        }

        const headerRow = ws.getRow(1);
        const headers: string[] = [];
        headerRow.eachCell({ includeEmpty: true }, (cell, col) => {
          headers[col - 1] = String(cell.value ?? '').trim();
        });

        for (let r = 2; r <= ws.rowCount; r += 1) {
          const row = ws.getRow(r);
          const obj: Record<string, any> = {};
          headers.forEach((header, idx) => {
            const cellVal = row.getCell(idx + 1).value as any;
            if (cellVal && typeof cellVal === 'object' && 'result' in cellVal) obj[header] = String(cellVal.result ?? '');
            else if (cellVal && typeof cellVal === 'object' && 'text' in cellVal) obj[header] = String(cellVal.text ?? '');
            else obj[header] = String(cellVal ?? '');
          });
          rows.push(obj);
        }
      } else {
        showWarning('Upload CSV or Excel file for Public Details.');
        return;
      }

      const detailsByKey = new Map<string, { aadhar: string; mobile: string; address: string }>();
      rows.forEach((row) => {
        const appKey = findObjectKey(row, ['App. No.', 'Application Number', 'App No']);
        const nameKey = findObjectKey(row, ['Name', 'Beneficiary Name']);
        const qtyKey = findObjectKey(row, ['QUANTITY', 'Quantity']);
        const aadharKey = findObjectKey(row, ['Aadhar (Without Space)', 'Aadhar', 'Aadhaar']);
        const addressKey = findObjectKey(row, ['Address']);
        const mobileKey = findObjectKey(row, ['Mobile', 'Mobile No']);

        const qty = qtyKey ? parseNumber(row[qtyKey]) : 1;
        if (qty === 0) return;

        const appNo = String(appKey ? row[appKey] : '').trim();
        const name = String(nameKey ? row[nameKey] : '').trim();
        if (!appNo || !name) return;

        detailsByKey.set(`${normalizeText(appNo)}||${normalizeText(name)}`, {
          aadhar: String(aadharKey ? row[aadharKey] : '').trim(),
          mobile: String(mobileKey ? row[mobileKey] : '').trim(),
          address: String(addressKey ? row[addressKey] : '').trim(),
        });
      });

      setPublicAckRows((prev) =>
        prev.map((row) => {
          const key = `${normalizeText(row.applicationNumber)}||${normalizeText(row.beneficiaryName)}`;
          const details = detailsByKey.get(key);
          if (!details) return row;
          return {
            ...row,
            aadharNumber: details.aadhar || row.aadharNumber || '0',
            mobile: details.mobile || row.mobile || '0',
            address: details.address || row.address || 'Add',
          };
        })
      );

      setPublicDetailsFileName(file.name);
      showSuccess('Public details merged into acknowledgment form rows.');
    } catch (error) {
      console.error('Failed to load public details file:', error);
      showError('Failed to load public details file.');
    } finally {
      setIsLoadingPublicDetails(false);
    }
  };

  const handleLoadFromDb = async () => {
    try {
      setIsLoadingDb(true);
      setSourceMode('db');
      const data = await fetchSeatAllocationRows(DEFAULT_SESSION_NAME);
      if (!data.length) {
        showWarning('No Seat Allocation rows found in DB.');
        setRows([]);
        return;
      }

      const mapped: TokenRow[] = data.map((row) => {
        const master = (row.master_row || {}) as Record<string, any>;
        const sequenceNo = parseNumber(master['Sequence No']);
        return {
          sourceId: row.id,
          applicationNumber: row.application_number || String(master['Application Number'] || master['App No'] || ''),
          district: row.district || String(master['District'] || ''),
          beneficiaryType: row.beneficiary_type || String(master['Beneficiary Type'] || ''),
          beneficiaryName: row.beneficiary_name || String(master['Beneficiary Name'] || ''),
          requestedItem: row.requested_item || String(master['Requested Item'] || master['Item'] || ''),
          itemType: String(row.item_type || master['Item Type'] || ''),
          quantity: parseNumber(row.quantity),
          waitingHallQuantity: parseNumber(row.waiting_hall_quantity),
          tokenQuantity: parseNumber(row.token_quantity),
          sequenceNo: sequenceNo > 0 ? sequenceNo : 999999,
          aadharNumber: String(master['Aadhar No'] || master['Aadhaar No'] || ''),
          notes: String(master['Notes'] || master['Comments'] || ''),
          masterRow: master,
          masterHeaders: (row.master_headers || []) as string[],
        };
      });

      setRows(mapped);
      setSourceFileName(data[0]?.source_file_name || 'seat_allocation_db');
      showSuccess(`Loaded ${mapped.length} row(s) from DB.`);
    } catch (error) {
      console.error('Failed to load token source from DB:', error);
      showError('Failed to load from Seat Allocation DB.');
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
      const idx = new Map(headers.map((h, i) => [h, i]));

      const appHeader = findHeaderName(headers, ['Application Number', 'App No']);
      const districtHeader = findHeaderName(headers, ['District']);
      const typeHeader = findHeaderName(headers, ['Beneficiary Type']);
      const beneficiaryHeader = findHeaderName(headers, ['Beneficiary Name', 'Name of Beneficiary', 'Name']);
      const itemHeader = findHeaderName(headers, ['Requested Item', 'Item', 'Article', 'Article Name']);
      const itemTypeHeader = findHeaderName(headers, ['Item Type']);
      const quantityHeader = findHeaderName(headers, ['Quantity']);
      const waitingHeader = findHeaderName(headers, ['Waiting Hall Quantity']);
      const tokenHeader = findHeaderName(headers, ['Token Quantity']);
      const sequenceHeader = findHeaderName(headers, ['Sequence No', 'Sequence List']);
      const aadharHeader = findHeaderName(headers, ['Aadhar No', 'Aadhaar No']);
      const notesHeader = findHeaderName(headers, ['Notes', 'Comments']);

      if (!itemHeader || !tokenHeader || !waitingHeader) {
        showError('Missing required columns: Item, Waiting Hall Quantity, Token Quantity.');
        return;
      }

      const mapped: TokenRow[] = parsed
        .slice(1)
        .map((cells) => ({
          applicationNumber: appHeader ? String(cells[idx.get(appHeader) || 0] || '').trim() : '',
          district: districtHeader ? String(cells[idx.get(districtHeader) || 0] || '').trim() : '',
          beneficiaryType: typeHeader ? String(cells[idx.get(typeHeader) || 0] || '').trim() : '',
          beneficiaryName: beneficiaryHeader ? String(cells[idx.get(beneficiaryHeader) || 0] || '').trim() : '',
          requestedItem: String(cells[idx.get(itemHeader) || 0] || '').trim(),
          itemType: itemTypeHeader ? String(cells[idx.get(itemTypeHeader) || 0] || '').trim() : '',
          quantity: quantityHeader ? parseNumber(cells[idx.get(quantityHeader) || 0]) : 0,
          waitingHallQuantity: parseNumber(cells[idx.get(waitingHeader) || 0]),
          tokenQuantity: parseNumber(cells[idx.get(tokenHeader) || 0]),
          sequenceNo: sequenceHeader ? parseNumber(cells[idx.get(sequenceHeader) || 0]) || 999999 : 999999,
          aadharNumber: aadharHeader ? String(cells[idx.get(aadharHeader) || 0] || '').trim() : '',
          notes: notesHeader ? String(cells[idx.get(notesHeader) || 0] || '').trim() : '',
          masterRow: headers.reduce((acc, header, headerIndex) => {
            acc[header] = cells[headerIndex] ?? '';
            return acc;
          }, {} as Record<string, any>),
          masterHeaders: headers,
        }))
        .filter((r) => r.requestedItem);

      setRows(mapped);
      setSourceFileName(file.name);
      showSuccess(`Loaded ${mapped.length} row(s) from CSV.`);
    } catch (error) {
      console.error('Failed to parse token source CSV:', error);
      showError('Failed to parse CSV.');
    } finally {
      setIsLoadingCsv(false);
    }
  };

  const exportGeneratedTokenFile = () => {
    if (!generatedRows.length) {
      showWarning('No token rows found.');
      return;
    }
    exportToCSV(
      generatedRows.map((row) => ({
        'Application Number': row.applicationNumber,
        District: row.district,
        'Beneficiary Type': toLegacyBeneficiaryType(row.beneficiaryType),
        Name: row.beneficiaryName,
        'Article Name': row.requestedItem,
        'ITEM TYPE': row.itemType,
        Quantity: row.quantity,
        'Waiting Hall Quantity': row.waitingHallQuantity,
        'Token Quantity': row.tokenQuantity,
        'Sequence List': row.sequenceNo === 999999 ? '' : row.sequenceNo,
        'Start Token No.': row.startTokenNo,
        'End Token No.': row.endTokenNo,
        'Token Print for ARTL': row.tokenPrintForArticle,
        'Label Size': row.labelSize,
        'Aadhar No': row.aadharNumber,
        Notes: row.notes,
      })),
      'Generated_token_V4',
      [
        'Application Number',
        'District',
        'Beneficiary Type',
        'Name',
        'Article Name',
        'ITEM TYPE',
        'Quantity',
        'Waiting Hall Quantity',
        'Token Quantity',
        'Sequence List',
        'Start Token No.',
        'End Token No.',
        'Token Print for ARTL',
        'Label Size',
        'Aadhar No',
        'Notes',
      ],
      showWarning
    );
    showSuccess('Generated token file exported.');
  };

  const exportBeneficiaryTokens = () => {
    if (!generatedRows.length) {
      showWarning('No token rows found.');
      return;
    }
    exportToCSV(
      generatedRows.map((row, index) => ({
        'Token No': index + 1,
        'Sequence No': row.sequenceNo === 999999 ? '' : row.sequenceNo,
        'Beneficiary Type': row.beneficiaryType,
        District: row.district,
        'Application Number': row.applicationNumber,
        'Beneficiary Name': row.beneficiaryName,
        Item: row.requestedItem,
        'Token Quantity': row.tokenQuantity,
        'Start Token No.': row.startTokenNo,
        'End Token No.': row.endTokenNo,
      })),
      'Generated_token_V4_All_List',
      [
        'Token No',
        'Sequence No',
        'Beneficiary Type',
        'District',
        'Application Number',
        'Beneficiary Name',
        'Item',
        'Token Quantity',
        'Start Token No.',
        'End Token No.',
      ],
      showWarning
    );
    showSuccess('Beneficiary token list exported.');
  };

  const exportDistrictAllList = () => {
    const districtRows = generatedRows.filter((r) => normalizeText(r.beneficiaryType) === 'district');
    if (!districtRows.length) {
      showWarning('No district token rows found.');
      return;
    }
    exportToCSV(
      districtRows.map((row) => ({
        'Sequence No': row.sequenceNo === 999999 ? '' : row.sequenceNo,
        District: row.district,
        'Application Number': row.applicationNumber,
        Name: row.beneficiaryName,
        'Article Name': row.requestedItem,
        'Token Quantity': row.tokenQuantity,
        'Start Token No.': row.startTokenNo,
        'End Token No.': row.endTokenNo,
      })),
      'Generated_token_V4_District_All_List',
      [
        'Sequence No',
        'District',
        'Application Number',
        'Name',
        'Article Name',
        'Token Quantity',
        'Start Token No.',
        'End Token No.',
      ],
      showWarning
    );
    showSuccess('District list exported.');
  };

  const exportInstitutionList = () => {
    const rowsToExport = generatedRows.filter((r) => isInstitutionType(r.beneficiaryType));
    if (!rowsToExport.length) {
      showWarning('No institution token rows found.');
      return;
    }
    exportToCSV(
      rowsToExport.map((row) => ({
        'Sequence No': row.sequenceNo === 999999 ? '' : row.sequenceNo,
        District: row.district,
        'Application Number': row.applicationNumber,
        Name: row.beneficiaryName,
        'Article Name': row.requestedItem,
        'Token Quantity': row.tokenQuantity,
        'Start Token No.': row.startTokenNo,
        'End Token No.': row.endTokenNo,
      })),
      'Generated_token_V4_Institution_List',
      [
        'Sequence No',
        'District',
        'Application Number',
        'Name',
        'Article Name',
        'Token Quantity',
        'Start Token No.',
        'End Token No.',
      ],
      showWarning
    );
    showSuccess('Institution list exported.');
  };

  const exportArticleWiseList = () => {
    const articleRows = generatedRows.filter((r) => normalizeText(r.itemType) === 'article');
    if (!articleRows.length) {
      showWarning('No article rows found.');
      return;
    }
    exportToCSV(
      articleRows.map((row) => ({
        'Sequence No': row.sequenceNo === 999999 ? '' : row.sequenceNo,
        'Article Name': row.requestedItem,
        District: row.district,
        'Beneficiary Type': row.beneficiaryType,
        'Application Number': row.applicationNumber,
        Name: row.beneficiaryName,
        'Token Quantity': row.tokenQuantity,
        'Start Token No.': row.startTokenNo,
        'End Token No.': row.endTokenNo,
        'Label Size': row.labelSize,
      })),
      'Generated_token_V4_Articles_list',
      [
        'Sequence No',
        'Article Name',
        'District',
        'Beneficiary Type',
        'Application Number',
        'Name',
        'Token Quantity',
        'Start Token No.',
        'End Token No.',
        'Label Size',
      ],
      showWarning
    );
    showSuccess('Article-wise list exported.');
  };

  const exportStickerList = (packSize: 2 | 12) => {
    const tokenRows = generatedRows.filter((r) => r.tokenQuantity > 0 && r.labelSize === `${packSize}L`);
    if (!tokenRows.length) {
      showWarning(`No ${packSize}L sticker rows found.`);
      return;
    }

    const exportRows = tokenRows.flatMap((row) => {
      const tokens = Array.from({ length: row.tokenQuantity }, (_, i) => row.startTokenNo + i);
      return tokens.map((tokenNo) => ({
        'Sequence No': row.sequenceNo === 999999 ? '' : row.sequenceNo,
        Item: row.requestedItem,
        District: row.district,
        'Application Number': row.applicationNumber,
        'Beneficiary Name': row.beneficiaryName,
        'Token No': tokenNo,
        'Sticker Type': `${packSize}L`,
      }));
    });

    exportToCSV(
      exportRows,
      `token-stickers-${packSize}l`,
      ['Sequence No', 'Item', 'District', 'Application Number', 'Beneficiary Name', 'Token No', 'Sticker Type'],
      showWarning
    );
    showSuccess(`${packSize}L sticker list exported.`);
  };

  const exportPrintLabels = async (kind: 'articles' | 'badges' | 'chairs') => {
    try {
      setIsGeneratingLabels(true);
      const printedCount = await downloadNotebookLabelsByType(generatedRows, kind, printLayout);
      if (!printedCount) {
        showWarning(`No rows found for ${kind} labels.`);
        return;
      }
      showSuccess(`${kind} labels PDF generated (${printLayout}) with ${printedCount} labels.`);
    } catch (error) {
      console.error(`Failed to generate ${kind} labels PDF:`, error);
      showError(`Failed to generate ${kind} labels PDF.`);
    } finally {
      setIsGeneratingLabels(false);
    }
  };

  const saveGeneratedToDb = async () => {
    if (sourceMode !== 'db') {
      showWarning('DB save works only for rows loaded from DB.');
      return;
    }
    if (!generatedRows.length) {
      showWarning('No token rows to save.');
      return;
    }

    const rowsToUpdate = generatedRows
      .filter((row) => row.sourceId)
      .map((row) => {
        const nextMasterRow = {
          ...row.masterRow,
          'Waiting Hall Quantity': row.waitingHallQuantity,
          'Token Quantity': row.tokenQuantity,
          'Sequence No': row.sequenceNo === 999999 ? '' : row.sequenceNo,
          'Start Token No.': row.startTokenNo,
          'End Token No.': row.endTokenNo,
          'Token Print for ARTL': row.tokenPrintForArticle,
          'Label Size': row.labelSize,
        };
        const nextHeaders = Array.from(
          new Set([
            ...row.masterHeaders,
            'Waiting Hall Quantity',
            'Token Quantity',
            'Sequence No',
            'Start Token No.',
            'End Token No.',
            'Token Print for ARTL',
            'Label Size',
          ])
        );
        return {
          id: row.sourceId as string,
          master_row: nextMasterRow,
          master_headers: nextHeaders,
        };
      });

    if (!rowsToUpdate.length) {
      showWarning('No DB-linked rows available to save.');
      return;
    }

    try {
      setIsSavingDb(true);
      await updateSeatAllocationSequenceData(rowsToUpdate);
      showSuccess(`Saved generated token fields for ${rowsToUpdate.length} row(s) to DB.`);
    } catch (error) {
      console.error('Failed to save generated token data to DB:', error);
      showError('Failed to save generated token file into DB.');
    } finally {
      setIsSavingDb(false);
    }
  };

  const exportVipChairLabels = () => {
    const tokenRows = generatedRows.filter((r) => r.tokenQuantity > 0);
    if (!tokenRows.length) {
      showWarning('No token rows found.');
      return;
    }

    exportToCSV(
      tokenRows.map((row, index) => ({
        'Chair No': index + 1,
        VIP: row.notes.toLowerCase().includes('vip') ? 'Yes' : 'No',
        'Beneficiary Type': row.beneficiaryType,
        District: row.district,
        'Application Number': row.applicationNumber,
        'Beneficiary Name': row.beneficiaryName,
        Item: row.requestedItem,
        'Start Token No.': row.startTokenNo,
        'End Token No.': row.endTokenNo,
      })),
      'Generated_token_V4_Chair_Details',
      ['Chair No', 'VIP', 'Beneficiary Type', 'District', 'Application Number', 'Beneficiary Name', 'Item', 'Start Token No.', 'End Token No.'],
      showWarning
    );
    showSuccess('VIP/Chair labels exported.');
  };

  const exportPublicAcknowledgment = () => {
    if (!publicAckRows.length) {
      showWarning('No public waiting-hall rows found.');
      return;
    }

    exportToCSV(
      publicAckRows.map((row) => ({
        'Application Number': row.applicationNumber,
        'Name of Beneficiary': row.beneficiaryName,
        'Aadhar No': row.aadharNumber,
        Mobile: row.mobile,
        Address: row.address,
        Item: row.item,
        'Waiting Hall Quantity': row.waitingHallQuantity,
        District: row.district,
        'Token Start No.': row.tokenStartNo,
        'Token End No.': row.tokenEndNo,
        Notes: row.notes,
      })),
      'Public_Acknowledgment_Autofill',
      ['Application Number', 'Name of Beneficiary', 'Aadhar No', 'Mobile', 'Address', 'Item', 'Waiting Hall Quantity', 'District', 'Token Start No.', 'Token End No.', 'Notes'],
      showWarning
    );
    showSuccess('Public acknowledgment file exported (with edits).');
  };

  return (
    <div className="p-3 sm:p-4">
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-3 sm:p-4 mb-3 shadow-sm">
        <div className="flex flex-col gap-3">
          <div className="border-b border-gray-200 dark:border-gray-700 pb-2">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
              <h1 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-white">Tokens</h1>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={handleLoadFromDb}
                  disabled={isLoadingDb}
                  className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50"
                >
                  <RefreshCw className={`w-4 h-4 ${isLoadingDb ? 'animate-spin' : ''}`} />
                  Use Sequenced DB
                </button>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isLoadingCsv}
                  className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm disabled:opacity-50"
                >
                  <FileUp className="w-4 h-4" />
                  {isLoadingCsv ? 'Uploading...' : 'Upload Sequenced CSV'}
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

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <div className="flex flex-wrap items-center gap-4 text-sm text-gray-600 dark:text-gray-300">
              <span>Source: <strong>{sourceMode === 'db' ? 'DB' : 'CSV'}</strong></span>
              <span>Rows: <strong>{rows.length}</strong></span>
              <span>Token Rows: <strong>{generatedRows.length}</strong></span>
              {sourceFileName ? <span>File: <strong>{sourceFileName}</strong></span> : null}
            </div>
            <div className="flex items-center gap-2 justify-start lg:justify-end">
              <label className="text-sm text-gray-700 dark:text-gray-200">Start Token No</label>
              <input
                type="number"
                min={1}
                value={startTokenNo}
                onChange={(e) => setStartTokenNo(Math.max(1, parseInt(e.target.value || '1', 10)))}
                className="w-28 px-2 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm"
              />
              <label className="text-sm text-gray-700 dark:text-gray-200 ml-2">Print Layout</label>
              <select
                value={printLayout}
                onChange={(e) => setPrintLayout(e.target.value as LabelLayout)}
                className="w-36 px-2 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm"
              >
                <option value="continuous">Continuous</option>
                <option value="separate">Separate</option>
              </select>
            </div>
          </div>

          <div>
            <label className="text-sm font-medium text-gray-800 dark:text-gray-100">
              2L Label Items (one per line)
            </label>
            <textarea
              value={bigItemsInput}
              onChange={(e) => setBigItemsInput(e.target.value)}
              rows={4}
              className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm"
            />
          </div>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-3 sm:p-4 mb-3 shadow-sm">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Token Data Exports</h2>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={saveGeneratedToDb}
            disabled={sourceMode !== 'db' || isSavingDb}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-indigo-300 text-indigo-700 dark:text-indigo-300 text-sm hover:bg-indigo-50 dark:hover:bg-indigo-900/30 disabled:opacity-50"
          >
            <Save className="w-4 h-4" />
            {isSavingDb ? 'Saving...' : 'Save Generated Tokens to DB'}
          </button>
          <button type="button" onClick={exportGeneratedTokenFile} className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-blue-300 text-blue-700 dark:text-blue-300 text-sm hover:bg-blue-50 dark:hover:bg-blue-900/30">
            <Download className="w-4 h-4" />
            Generated Token File
          </button>
          <button type="button" onClick={exportBeneficiaryTokens} className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-green-300 text-green-700 dark:text-green-300 text-sm hover:bg-green-50 dark:hover:bg-green-900/30">
            <Download className="w-4 h-4" />
            All Beneficiary Token List
          </button>
          <button type="button" onClick={exportDistrictAllList} className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-emerald-300 text-emerald-700 dark:text-emerald-300 text-sm hover:bg-emerald-50 dark:hover:bg-emerald-900/30">
            <Download className="w-4 h-4" />
            District All List
          </button>
          <button type="button" onClick={exportInstitutionList} className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-cyan-300 text-cyan-700 dark:text-cyan-300 text-sm hover:bg-cyan-50 dark:hover:bg-cyan-900/30">
            <Download className="w-4 h-4" />
            Institution List
          </button>
          <button type="button" onClick={exportArticleWiseList} className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-orange-300 text-orange-700 dark:text-orange-300 text-sm hover:bg-orange-50 dark:hover:bg-orange-900/30">
            <Download className="w-4 h-4" />
            Articles List
          </button>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-3 sm:p-4 mb-3 shadow-sm">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Label / Form Exports</h2>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void exportPrintLabels('articles')}
            disabled={isGeneratingLabels}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-rose-300 text-rose-700 dark:text-rose-300 text-sm hover:bg-rose-50 dark:hover:bg-rose-900/30 disabled:opacity-50"
          >
            <Download className="w-4 h-4" />
            Article Labels ({printLayout})
          </button>
          <button
            type="button"
            onClick={() => void exportPrintLabels('badges')}
            disabled={isGeneratingLabels}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-sky-300 text-sky-700 dark:text-sky-300 text-sm hover:bg-sky-50 dark:hover:bg-sky-900/30 disabled:opacity-50"
          >
            <Download className="w-4 h-4" />
            Badge Labels ({printLayout})
          </button>
          <button
            type="button"
            onClick={() => void exportPrintLabels('chairs')}
            disabled={isGeneratingLabels}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-fuchsia-300 text-fuchsia-700 dark:text-fuchsia-300 text-sm hover:bg-fuchsia-50 dark:hover:bg-fuchsia-900/30 disabled:opacity-50"
          >
            <Download className="w-4 h-4" />
            Chair Labels ({printLayout})
          </button>
          <button type="button" onClick={() => exportStickerList(2)} className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-amber-300 text-amber-700 dark:text-amber-300 text-sm hover:bg-amber-50 dark:hover:bg-amber-900/30">
            <Download className="w-4 h-4" />
            Sticker 2L
          </button>
          <button type="button" onClick={() => exportStickerList(12)} className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-amber-300 text-amber-700 dark:text-amber-300 text-sm hover:bg-amber-50 dark:hover:bg-amber-900/30">
            <Download className="w-4 h-4" />
            Sticker 12L
          </button>
          <button type="button" onClick={exportVipChairLabels} className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-purple-300 text-purple-700 dark:text-purple-300 text-sm hover:bg-purple-50 dark:hover:bg-purple-900/30">
            <Download className="w-4 h-4" />
            VIP / Chair Labels
          </button>
          <button type="button" onClick={exportPublicAcknowledgment} className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-indigo-300 text-indigo-700 dark:text-indigo-300 text-sm hover:bg-indigo-50 dark:hover:bg-indigo-900/30">
            <Download className="w-4 h-4" />
            Public Acknowledgment
          </button>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-3 sm:p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">Public Acknowledgment (Editable)</h2>
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <button
            type="button"
            onClick={() => publicDetailsFileInputRef.current?.click()}
            disabled={isLoadingPublicDetails}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-indigo-300 text-indigo-700 dark:text-indigo-300 text-sm hover:bg-indigo-50 dark:hover:bg-indigo-900/30 disabled:opacity-50"
          >
            <FileUp className="w-4 h-4" />
            {isLoadingPublicDetails ? 'Loading Public Details...' : 'Upload Public Details (CSV/XLSX)'}
          </button>
          {publicDetailsFileName ? (
            <span className="text-xs text-gray-600 dark:text-gray-300">Merged file: <strong>{publicDetailsFileName}</strong></span>
          ) : null}
          <input
            ref={publicDetailsFileInputRef}
            type="file"
            accept=".csv,.xlsx,.xls"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void handleUploadPublicDetails(file);
              e.currentTarget.value = '';
            }}
          />
        </div>
        <div className="max-h-72 overflow-auto border border-gray-200 dark:border-gray-700 rounded-lg">
          {publicAckRows.length === 0 ? (
            <div className="p-3 text-sm text-gray-500 dark:text-gray-400">No public waiting-hall rows found.</div>
          ) : (
            <table className="w-full text-xs">
              <thead className="bg-gray-50 dark:bg-gray-800">
                <tr>
                  <th className="p-2 text-left">App No</th>
                  <th className="p-2 text-left">Name</th>
                  <th className="p-2 text-left">Aadhar</th>
                  <th className="p-2 text-left">Mobile</th>
                  <th className="p-2 text-left">Address</th>
                  <th className="p-2 text-left">Item</th>
                  <th className="p-2 text-left">Waiting</th>
                  <th className="p-2 text-left">District</th>
                  <th className="p-2 text-left">Token Start</th>
                  <th className="p-2 text-left">Token End</th>
                  <th className="p-2 text-left">Notes</th>
                </tr>
              </thead>
              <tbody>
                {publicAckRows.map((row) => (
                  <tr key={row.id} className="border-t border-gray-100 dark:border-gray-800">
                    <td className="p-2 whitespace-nowrap">{row.applicationNumber}</td>
                    <td className="p-1">
                      <input value={row.beneficiaryName} onChange={(e) => updatePublicAckRow(row.id, 'beneficiaryName', e.target.value)} className="w-44 px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800" />
                    </td>
                    <td className="p-1">
                      <input value={row.aadharNumber} onChange={(e) => updatePublicAckRow(row.id, 'aadharNumber', e.target.value)} className="w-32 px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800" />
                    </td>
                    <td className="p-1">
                      <input value={row.mobile} onChange={(e) => updatePublicAckRow(row.id, 'mobile', e.target.value)} className="w-28 px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800" />
                    </td>
                    <td className="p-1">
                      <input value={row.address} onChange={(e) => updatePublicAckRow(row.id, 'address', e.target.value)} className="w-44 px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800" />
                    </td>
                    <td className="p-1">
                      <input value={row.item} onChange={(e) => updatePublicAckRow(row.id, 'item', e.target.value)} className="w-40 px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800" />
                    </td>
                    <td className="p-1">
                      <input type="number" min={0} value={row.waitingHallQuantity} onChange={(e) => updatePublicAckRow(row.id, 'waitingHallQuantity', e.target.value)} className="w-20 px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800" />
                    </td>
                    <td className="p-1">
                      <input value={row.district} onChange={(e) => updatePublicAckRow(row.id, 'district', e.target.value)} className="w-28 px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800" />
                    </td>
                    <td className="p-2 whitespace-nowrap">{row.tokenStartNo}</td>
                    <td className="p-2 whitespace-nowrap">{row.tokenEndNo}</td>
                    <td className="p-1">
                      <input value={row.notes} onChange={(e) => updatePublicAckRow(row.id, 'notes', e.target.value)} className="w-44 px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-3 sm:p-4 shadow-sm mt-3">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">Quick Check</h2>
        <div className="text-sm text-gray-600 dark:text-gray-300 grid grid-cols-1 md:grid-cols-3 gap-2">
          <div>Total Waiting Hall Qty: <strong>{usableRows.reduce((sum, r) => sum + r.waitingHallQuantity, 0)}</strong></div>
          <div>Total Token Qty: <strong>{generatedRows.reduce((sum, r) => sum + r.tokenQuantity, 0)}</strong></div>
          <div>Last Token No: <strong>{generatedRows.length ? generatedRows[generatedRows.length - 1].endTokenNo : 0}</strong></div>
        </div>
      </div>
    </div>
  );
};

export default Phase2TokenModule;
