import React from 'react';
import { Document, Page, StyleSheet, Text, View, pdf } from '@react-pdf/renderer';

export type LabelLayout = 'separate' | 'continuous';

export type NotebookInputRow = {
  sourceId?: string;
  applicationNumber: string;
  district: string;
  beneficiaryType: string;
  beneficiaryName: string;
  requestedItem: string;
  itemType: string;
  quantity: number;
  waitingHallQuantity: number;
  tokenQuantity: number;
  sequenceNo: number;
  aadharNumber: string;
  notes: string;
  masterRow: Record<string, any>;
  masterHeaders: string[];
};

export type NotebookTokenRow = NotebookInputRow & {
  startTokenNo: number;
  endTokenNo: number;
  tokenPrintForArticle: number;
  labelSize: '2L' | '12L';
};

type LabelRecord = {
  token: string;
  district: string;
  article: string;
  groupKey: string;
};

const normalizeText = (value: string): string => value.trim().toLowerCase().replace(/\s+/g, ' ');
const toTitleCase = (value: string): string =>
  value
    .toLowerCase()
    .split(' ')
    .map((part) => (part ? part.charAt(0).toUpperCase() + part.slice(1) : part))
    .join(' ');

const mmToPt = (mm: number) => (mm * 72) / 25.4;
const A4_WIDTH = 595.28;
const A4_HEIGHT = 841.89;

const STD_TOP = mmToPt(9);
const STD_LEFT = mmToPt(4);
const STD_VERTICAL_PITCH = mmToPt(47);
const STD_HORIZONTAL_PITCH = mmToPt(102);
const STD_LABEL_H = mmToPt(44);
const STD_LABEL_W = mmToPt(100);

const L2_TOP = mmToPt(2.5);
const L2_LEFT = mmToPt(5);
const L2_VERTICAL_PITCH = mmToPt(146);
const L2_HORIZONTAL_PITCH = mmToPt(200);
const L2_LABEL_H = mmToPt(146);
const L2_LABEL_W = mmToPt(200);

const beneficiaryRenameMap = new Map<string, string>(
  Object.entries({
    'P 300 - E.Sangeethaneivantham, Thiruvannmalai': 'P 300 - E.Sangeethaneivantham',
    'Adhiparasakthi Institutions': 'AP Institutions',
    'Adhiparasakthi Mat Hr.Sec.School': 'APMHSS',
    'Adhiparasakthi Annai Illam': 'Annai Illam',
  })
);

const articleRenameMap = new Map<string, string>(
  Object.entries({
    'Agri Power Sprayer (2 STK)': 'Agri Power Sprayer 2S',
    'Agri Power Sprayer (4 STK)': 'Agri Power Sprayer 4S',
    'Air Conditioner 1 Tonne': 'Air Conditioner 1T',
    'Aluminium Idli Making Box': 'Alu Idli Making Box',
    'Aluminium Vessels Set - Big': 'Alu Vessels Set - Big',
    'Aluminium Vessels Sets': 'Alu Vessels Sets',
    'Bore well Pump(5 HP) / DOL Starter': 'Bore Well Pump 5HP',
    'Bosch Electrician Kit 10 Re': 'Bosch 10 RE Kit',
    'Bosch Electrician Kit 13 Re': 'Bosch 13 RE Kit',
    'Bosch Rotary Hammer GBH 220': 'Bosch RH GBH 220',
    'Colour Printer HP Smart Tank 760 All in one': 'HP Smart Tank Printer',
    'Front Load Business Tricycle': 'Front Load Tricycle',
    'Gaja Hi tech Agro 6.5 HP Pump': 'Gaja 6.5 HP Pump',
    'Gp Welding Machine Arc 200': 'Gp Welding Arc 200',
    'Hand Sewing Machine with Motor': 'Hand Sewing Machine/Motor',
    'HP Printer 126NW (Heavy, All in 1)': 'HP Printer 126NW',
    'Iron Ms Stove 2 Burner': 'Stove 2 Burner',
    'Pushcart + Idli box + MS Burner stove': 'Pushcart/Idli box/MS Burner stove',
    'Sewing Machine Universal ZigZag': 'Sewing Machine ZigZag',
    'Table Top Tilting Grinder 2 Ltr': 'Table Top Tilting Grinder 2L',
    'Table Top Wet Grinder 2 Ltr': 'Table Top Wet Grinder 2L',
    'Table Top Wet Grinder 3Ltr': 'Table Top Wet Grinder 3L',
    'Tiffen Set + Idli Box +2 burner stove': 'Tiffen Set/Idli Box/2 burner stove',
    'TIFFEN SET + MS STOVE 2 BURNER': 'TIFFEN SET/2 BURNER',
    'Weighing Scale+ Bicycle+Basket for Fish Vendor': 'Fish Vendor Set',
    'Wet Grinder 2 Ltr (Hgt)': 'Wet Grinder 2L(Hgt)',
    'Wet Grinder 3 Ltrs': 'Wet Grinder 3L',
    'Wet Grinder 5 Ltrs': 'Wet Grinder 5L',
    'Wet Grinder Floor Model 2 Ltr': 'Wet Grinder Floor 2L',
    'Epson Printer L3250 (Lite)': 'Epson Printer L3250',
  })
);

const waitingHallOverrides = new Map<string, number>([
  ['project', 1],
  ['dictionary english - tamil', 498],
  ['sandalwood tree sapling', 298],
]);

const tokenPrintForceOffItems = new Set(
  ['Goat', 'Tree plant Saplings', 'Sandalwood tree Sapling', 'Fishing net', 'Rice 1000 Kgs'].map(normalizeText)
);

const cleanArticleDisplay = (value: string): string => {
  const titled = toTitleCase(String(value || '').trim());
  if (normalizeText(titled) === 'sewing machine ord') return 'Sewing Machine ORD';
  return titled;
};

const standardStyles = StyleSheet.create({
  page: { width: A4_WIDTH, height: A4_HEIGHT, position: 'relative', fontFamily: 'Arial' },
  label: { width: STD_LABEL_W, height: STD_LABEL_H, position: 'absolute' },
  token: { position: 'absolute', left: mmToPt(8), top: mmToPt(9), fontFamily: 'Arial', fontWeight: 700 },
  district: {
    position: 'absolute',
    left: STD_LABEL_W / 2,
    top: mmToPt(4),
    width: STD_LABEL_W / 2 - mmToPt(2),
    fontSize: 15,
    fontFamily: 'Arial',
    fontWeight: 700,
    textAlign: 'center',
  },
  article: {
    position: 'absolute',
    left: STD_LABEL_W / 2,
    top: mmToPt(24),
    width: STD_LABEL_W / 2 - mmToPt(2),
    fontSize: 15,
    fontFamily: 'Arial',
    fontWeight: 700,
    lineHeight: 1.1,
    textAlign: 'center',
  },
});

const large2LStyles = StyleSheet.create({
  page: { width: A4_WIDTH, height: A4_HEIGHT, position: 'relative', fontFamily: 'Arial' },
  label: { width: L2_LABEL_W, height: L2_LABEL_H, position: 'absolute' },
  token: { position: 'absolute', left: mmToPt(8), top: mmToPt(40), fontFamily: 'Arial', fontWeight: 700 },
  district: {
    position: 'absolute',
    left: L2_LABEL_W / 2,
    top: mmToPt(56),
    width: L2_LABEL_W / 2,
    fontSize: 35,
    fontFamily: 'Arial',
    fontWeight: 700,
    textAlign: 'center',
  },
  article: {
    position: 'absolute',
    left: L2_LABEL_W / 2,
    top: mmToPt(35),
    width: L2_LABEL_W / 2,
    fontSize: 35,
    fontFamily: 'Arial',
    fontWeight: 700,
    lineHeight: 1.1,
    textAlign: 'center',
  },
});

const projectStyles = StyleSheet.create({
  page: { width: A4_WIDTH, height: A4_HEIGHT, position: 'relative', fontFamily: 'Arial' },
  label: { width: STD_LABEL_W, height: STD_LABEL_H, position: 'absolute' },
  serial: { position: 'absolute', left: mmToPt(6), top: mmToPt(6), fontSize: 45, fontFamily: 'Arial', fontWeight: 700 },
  project: {
    position: 'absolute',
    left: STD_LABEL_W / 2,
    top: mmToPt(10),
    width: STD_LABEL_W / 2,
    textAlign: 'center',
    fontSize: 30,
    fontFamily: 'Arial',
    fontWeight: 700,
  },
});

const tokenFontSize = (token: string, large = false): number => {
  if (large) return token.length >= 4 ? 70 : 80;
  if (token.length >= 4) return 47;
  if (token.length === 3) return 50;
  return 60;
};

const chunk = <T,>(items: T[], size: number): T[][] => {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
};

const triggerDownload = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

const typeOrder = (beneficiaryType: string): number => {
  const t = normalizeText(beneficiaryType);
  if (t === 'district') return 1;
  if (t === 'public') return 2;
  if (t === 'institution' || t === 'institutions') return 3;
  if (t === 'others') return 4;
  return 9;
};

const standardSort = (a: NotebookInputRow, b: NotebookInputRow): number => {
  if (a.sequenceNo !== b.sequenceNo) return a.sequenceNo - b.sequenceNo;
  const typeDiff = typeOrder(a.beneficiaryType) - typeOrder(b.beneficiaryType);
  if (typeDiff !== 0) return typeDiff;
  return a.beneficiaryName.localeCompare(b.beneficiaryName, undefined, { sensitivity: 'base' });
};

export const buildNotebookTokenRows = (
  inputRows: NotebookInputRow[],
  startTokenNo: number,
  bigItemSet: Set<string>
): NotebookTokenRow[] => {
  const renamed = inputRows.map((row) => {
    const renamedName = beneficiaryRenameMap.get(row.beneficiaryName) ?? row.beneficiaryName;
    const renamedItem = articleRenameMap.get(row.requestedItem) ?? row.requestedItem;
    const overrideWaiting = waitingHallOverrides.get(normalizeText(renamedItem));
    const waitingHallQuantity = Number.isFinite(overrideWaiting as number)
      ? Math.max(0, Math.min(row.quantity, Number(overrideWaiting)))
      : Math.max(0, Number(row.waitingHallQuantity) || 0);
    const tokenQuantity = Math.max(0, (Number(row.quantity) || 0) - waitingHallQuantity);
    return {
      ...row,
      beneficiaryName: renamedName,
      requestedItem: renamedItem,
      waitingHallQuantity,
      tokenQuantity,
    };
  });

  const sorted = [...renamed].sort(standardSort);
  const zeroRows = sorted.filter((r) => r.tokenQuantity === 0);
  const tokenRows = sorted.filter((r) => r.tokenQuantity > 0);

  let nextToken = Math.max(1, Math.floor(startTokenNo || 1));
  const generatedTokenRows = tokenRows.map((row) => {
    const start = nextToken;
    const end = start + row.tokenQuantity - 1;
    nextToken = end + 1;

    const isArticle = normalizeText(row.itemType) === 'article';
    const tokenPrintForArticle =
      isArticle && !tokenPrintForceOffItems.has(normalizeText(row.requestedItem)) ? 1 : 0;
    const labelSize: '2L' | '12L' = bigItemSet.has(normalizeText(row.requestedItem)) ? '2L' : '12L';

    return {
      ...row,
      startTokenNo: start,
      endTokenNo: end,
      tokenPrintForArticle,
      labelSize,
    };
  });

  const generatedZeroRows: NotebookTokenRow[] = zeroRows.map((row) => {
    const isArticle = normalizeText(row.itemType) === 'article';
    const tokenPrintForArticle =
      isArticle && !tokenPrintForceOffItems.has(normalizeText(row.requestedItem)) ? 1 : 0;
    const labelSize: '2L' | '12L' = bigItemSet.has(normalizeText(row.requestedItem)) ? '2L' : '12L';
    return {
      ...row,
      startTokenNo: 0,
      endTokenNo: 0,
      tokenPrintForArticle,
      labelSize,
    };
  });

  return [...generatedTokenRows, ...generatedZeroRows].sort((a, b) => {
    if (a.sequenceNo !== b.sequenceNo) return a.sequenceNo - b.sequenceNo;
    const typeDiff = typeOrder(a.beneficiaryType) - typeOrder(b.beneficiaryType);
    if (typeDiff !== 0) return typeDiff;
    const nameDiff = a.beneficiaryName.localeCompare(b.beneficiaryName, undefined, { sensitivity: 'base' });
    if (nameDiff !== 0) return nameDiff;
    return a.startTokenNo - b.startTokenNo;
  });
};

const buildStandardLabels = (rows: NotebookTokenRow[]): LabelRecord[] => {
  const labels: LabelRecord[] = [];
  rows.forEach((row) => {
    if (row.tokenQuantity <= 0) return;
    const district = toTitleCase(row.beneficiaryName);
    const article = cleanArticleDisplay(row.requestedItem);
    for (let token = row.startTokenNo; token <= row.endTokenNo; token += 1) {
      labels.push({
        token: String(token),
        district,
        article,
        groupKey: article,
      });
    }
  });
  return labels;
};

const paginate = (labels: LabelRecord[], layout: LabelLayout): LabelRecord[][] => {
  if (layout === 'continuous') return chunk(labels, 12);
  const pages: LabelRecord[][] = [];
  let currentGroup = '';
  let groupLabels: LabelRecord[] = [];
  labels.forEach((label) => {
    if (label.groupKey !== currentGroup) {
      if (groupLabels.length > 0) pages.push(...chunk(groupLabels, 12));
      currentGroup = label.groupKey;
      groupLabels = [];
    }
    groupLabels.push(label);
  });
  if (groupLabels.length > 0) pages.push(...chunk(groupLabels, 12));
  return pages;
};

const StandardLabelDocument: React.FC<{ pages: LabelRecord[][] }> = ({ pages }) => (
  <Document>
    {pages.map((page, pageIdx) => (
      <Page key={`std-${pageIdx}`} size="A4" style={standardStyles.page}>
        {page.map((label, idx) => {
          const col = idx % 2;
          const row = Math.floor(idx / 2) % 6;
          const left = STD_LEFT + col * STD_HORIZONTAL_PITCH;
          const top = STD_TOP + row * STD_VERTICAL_PITCH;
          return (
            <View key={`std-label-${pageIdx}-${idx}-${label.token}`} style={[standardStyles.label, { left, top }]}>
              <Text style={[standardStyles.token, { fontSize: tokenFontSize(label.token) }]}>{label.token}</Text>
              <Text style={standardStyles.district}>{label.district}</Text>
              <Text style={standardStyles.article}>{label.article}</Text>
            </View>
          );
        })}
      </Page>
    ))}
  </Document>
);

const Large2LDocument: React.FC<{ pages: LabelRecord[][] }> = ({ pages }) => (
  <Document>
    {pages.map((page, pageIdx) => (
      <Page key={`2l-${pageIdx}`} size="A4" style={large2LStyles.page}>
        {page.map((label, idx) => {
          const col = idx % 1;
          const row = Math.floor(idx / 1) % 2;
          const left = L2_LEFT + col * L2_HORIZONTAL_PITCH;
          const top = L2_TOP + row * L2_VERTICAL_PITCH;
          return (
            <View key={`2l-label-${pageIdx}-${idx}-${label.token}`} style={[large2LStyles.label, { left, top }]}>
              <Text style={[large2LStyles.token, { fontSize: tokenFontSize(label.token, true) }]}>{label.token}</Text>
              <Text style={large2LStyles.district}>{label.district}</Text>
              <Text style={large2LStyles.article}>{label.article}</Text>
            </View>
          );
        })}
      </Page>
    ))}
  </Document>
);

const ProjectLabelDocument: React.FC<{ pages: Array<Array<{ serial: number; project: string }>> }> = ({ pages }) => (
  <Document>
    {pages.map((page, pageIdx) => (
      <Page key={`project-${pageIdx}`} size="A4" style={projectStyles.page}>
        {page.map((label, idx) => {
          const col = idx % 2;
          const row = Math.floor(idx / 2) % 6;
          const left = STD_LEFT + col * STD_HORIZONTAL_PITCH;
          const top = STD_TOP + row * STD_VERTICAL_PITCH;
          return (
            <View key={`project-label-${pageIdx}-${idx}`} style={[projectStyles.label, { left, top }]}>
              <Text style={projectStyles.serial}>{String(label.serial)}</Text>
              <Text style={projectStyles.project}>{label.project}</Text>
            </View>
          );
        })}
      </Page>
    ))}
  </Document>
);

const filterArticleRows = (rows: NotebookTokenRow[]): NotebookTokenRow[] =>
  rows.filter(
    (r) =>
      r.tokenQuantity > 0 &&
      r.tokenPrintForArticle === 1 &&
      !new Set(
        ['Steel Cupboard', 'Office Table 4X2', 'S Type Chair', 'Reception 4 Seater', 'Tiffen Set'].map(normalizeText)
      ).has(normalizeText(r.requestedItem))
  );

const downloadStandardPdf = async (
  rows: NotebookTokenRow[],
  layout: LabelLayout,
  fileName: string,
  groupBy: 'article' | 'district'
): Promise<number> => {
  const labels = buildStandardLabels(rows).map((label) => ({
    ...label,
    groupKey: groupBy === 'district' ? label.district : label.article,
  }));
  if (!labels.length) return 0;
  const pages = paginate(labels, layout);
  const blob = await pdf(<StandardLabelDocument pages={pages} />).toBlob();
  triggerDownload(blob, fileName);
  return labels.length;
};

const downloadLarge2L = async (rows: NotebookTokenRow[]): Promise<number> => {
  const labels = buildStandardLabels(rows.filter((r) => r.tokenQuantity > 0 && r.labelSize === '2L'));
  if (!labels.length) return 0;
  const pages = chunk(labels, 2);
  const blob = await pdf(<Large2LDocument pages={pages} />).toBlob();
  triggerDownload(blob, '2.Article_2L_Labels.pdf');
  return labels.length;
};

const downloadProject = async (rows: NotebookTokenRow[]): Promise<number> => {
  const primaryTotal = rows
    .filter(
      (row) => row.tokenQuantity > 0 && (normalizeText(row.requestedItem) === 'project' || normalizeText(row.itemType) === 'project')
    )
    .reduce((sum, row) => sum + row.tokenQuantity, 0);
  const fallbackTotal = rows
    .filter((row) => row.tokenQuantity > 0 && normalizeText(row.itemType) !== 'article')
    .reduce((sum, row) => sum + row.tokenQuantity, 0);
  const total = primaryTotal || fallbackTotal;
  if (!total) return 0;
  const data = Array.from({ length: total }, (_, i) => ({ serial: i + 1, project: 'Project' }));
  const pages = chunk(data, 12);
  const blob = await pdf(<ProjectLabelDocument pages={pages} />).toBlob();
  triggerDownload(blob, '6.Project_label.pdf');
  return total;
};

export const downloadNotebookLabelsByType = async (
  rows: NotebookTokenRow[],
  kind: 'articles' | 'chairs' | 'badges',
  layout: LabelLayout
): Promise<number> => {
  if (kind === 'articles') {
    return downloadStandardPdf(
      filterArticleRows(rows).map((row) => ({ ...row })),
      layout,
      layout === 'separate' ? '1.Article_Labels_S.pdf' : '1.Article_Labels_C.pdf',
      'article'
    );
  }
  if (kind === 'chairs') {
    return downloadStandardPdf(
      rows.filter((row) => row.tokenQuantity > 0 && row.tokenPrintForArticle === 1),
      layout,
      layout === 'separate' ? 'Chair_Labels_S.pdf' : 'Chair_Labels_C.pdf',
      'article'
    );
  }
  return downloadStandardPdf(rows.filter((row) => row.tokenQuantity > 0), layout, '5.PI_labels.pdf', 'district');
};

export const downloadNotebookPdfsInOrder = async (rows: NotebookTokenRow[]): Promise<Record<string, number>> => {
  const results: Record<string, number> = {};

  results['1.Article_Labels_S.pdf'] = await downloadStandardPdf(filterArticleRows(rows), 'separate', '1.Article_Labels_S.pdf', 'article');
  results['1.Article_Labels_C.pdf'] = await downloadStandardPdf(filterArticleRows(rows), 'continuous', '1.Article_Labels_C.pdf', 'article');

  const chairRows = rows.filter((row) => row.tokenQuantity > 0 && row.tokenPrintForArticle === 1);
  results['Chair_Labels_S.pdf'] = await downloadStandardPdf(chairRows, 'separate', 'Chair_Labels_S.pdf', 'article');
  results['Chair_Labels_C.pdf'] = await downloadStandardPdf(chairRows, 'continuous', 'Chair_Labels_C.pdf', 'article');

  results['2.Article_2L_Labels.pdf'] = await downloadLarge2L(rows);

  const districtRows = [...rows]
    .filter((row) => row.tokenQuantity > 0 && normalizeText(row.beneficiaryType) === 'district')
    .sort((a, b) => a.beneficiaryName.localeCompare(b.beneficiaryName, undefined, { sensitivity: 'base' }) || a.startTokenNo - b.startTokenNo);
  results['3.District_Labels.pdf'] = await downloadStandardPdf(districtRows, 'separate', '3.District_Labels.pdf', 'district');

  const othersRows = [...rows]
    .filter((row) => row.tokenQuantity > 0 && normalizeText(row.beneficiaryType) === 'others')
    .sort((a, b) => a.beneficiaryName.localeCompare(b.beneficiaryName, undefined, { sensitivity: 'base' }) || a.startTokenNo - b.startTokenNo);
  results['3.1.Others_Labels.pdf'] = await downloadStandardPdf(othersRows, 'continuous', '3.1.Others_Labels.pdf', 'district');

  const piRows = [...rows]
    .filter((row) => {
      const t = normalizeText(row.beneficiaryType);
      return row.tokenQuantity > 0 && (t === 'public' || t === 'institution' || t === 'institutions');
    })
    .sort((a, b) => a.beneficiaryName.localeCompare(b.beneficiaryName, undefined, { sensitivity: 'base' }) || a.startTokenNo - b.startTokenNo);
  results['5.PI_labels.pdf'] = await downloadStandardPdf(piRows, 'continuous', '5.PI_labels.pdf', 'district');

  results['6.Project_label.pdf'] = await downloadProject(rows);

  return results;
};
