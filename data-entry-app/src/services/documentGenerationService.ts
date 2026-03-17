import ExcelJS from 'exceljs';
import { supabase } from '../lib/supabase';
import { fetchFundRequestById, fetchPreviousFundRequestTotal, generatePurchaseOrderNumber, type FundRequestWithDetails } from './fundRequestService';
import { aidFundRequestConfig } from '../config/excelTemplateConfig';
import { pdf } from '@react-pdf/renderer';
import React from 'react';
import FundRequestPDFDocument from '../components/FundRequestPDFDocument';
import PurchaseOrderPDFDocument from '../components/PurchaseOrderPDFDocument';
import { formatDate, getBeneficiaryDisplayValue } from '../utils/fundRequestUtils';
import guruLogoPath from '../assets/guru-logo.jpg';
import signaturePath from '../assets/sign.jpg';

// Flag to enable/disable XLSX generation (currently disabled)
export const ENABLE_XLSX_GENERATION = false;

/**
 * Generate Fund Request PDF document
 */
export const generateFundRequestPDF = async (
  fundRequestId: string,
  _type: 'Aid' | 'Article',
  orientation: 'portrait' | 'landscape' = 'portrait'
): Promise<Blob> => {
  try {
    const fundRequest = await fetchFundRequestById(fundRequestId);
    if (!fundRequest) {
      throw new Error('Fund request not found');
    }

    // Calculate previous cumulative total
    let previousCumulative = 0;
    if (fundRequest.created_at && fundRequest.id) {
      previousCumulative = await fetchPreviousFundRequestTotal(fundRequest.id, fundRequest.created_at);
    }

    // Load logos as data URIs
    const { currentLogo, guruLogo, signature } = await loadLogosAsDataUri();

    // Generate PDF using React PDF
    const pdfDoc = React.createElement(FundRequestPDFDocument, {
      fundRequest,
      previousCumulative,
      logoDataUri: currentLogo,
      guruLogoDataUri: guruLogo,
      signatureDataUri: signature,
      orientation,
    }) as React.ReactElement;

    // Generate PDF blob
    const pdfBlob = await pdf(pdfDoc).toBlob();
    return pdfBlob;
  } catch (error) {
    console.error('Error generating fund request PDF:', error);
    throw error;
  }
};

/**
 * Generate Fund Request XLSX document (disabled by default)
 */
export const generateFundRequestXLSX = async (
  fundRequestId: string,
  type: 'Aid' | 'Article'
): Promise<Blob> => {
  try {
    const fundRequest = await fetchFundRequestById(fundRequestId);
    if (!fundRequest) {
      throw new Error('Fund request not found');
    }

    let workbook: ExcelJS.Workbook;

    if (type === 'Aid') {
      // Load template for Aid
      try {
        const response = await fetch('/model-docs/Fund Request - 6 Aid.xlsx');
        if (!response.ok) {
          throw new Error('Template file not found');
        }
        const arrayBuffer = await response.arrayBuffer();
        workbook = new ExcelJS.Workbook();
        await workbook.xlsx.load(arrayBuffer);
        
        // Get the first worksheet (template)
        const worksheet = workbook.worksheets[0];
        await populateAidFundRequestTemplate(worksheet, fundRequest);
      } catch (templateError) {
        console.warn('Failed to load template, creating new document:', templateError);
        // Fallback to creating new document
        workbook = new ExcelJS.Workbook();
        const worksheet = workbook.addWorksheet('Fund Request');
        await createAidFundRequestSheet(worksheet, fundRequest);
      }
    } else {
      workbook = new ExcelJS.Workbook();
      const worksheet = workbook.addWorksheet('Fund Request');
      await createArticleFundRequestSheet(worksheet, fundRequest);
    }

    // Generate buffer
    const buffer = await workbook.xlsx.writeBuffer();
    return new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
  } catch (error) {
    console.error('Error generating fund request XLSX:', error);
    throw error;
  }
};

/**
 * Generate Fund Request document for Aid or Article
 * Defaults to PDF generation (XLSX is disabled)
 */
export const generateFundRequestDocument = async (
  fundRequestId: string,
  type: 'Aid' | 'Article',
  orientation: 'portrait' | 'landscape' = 'portrait'
): Promise<Blob> => {
  // Use PDF by default, XLSX is disabled
  if (ENABLE_XLSX_GENERATION) {
    return generateFundRequestXLSX(fundRequestId, type);
  } else {
    return generateFundRequestPDF(fundRequestId, type, orientation);
  }
};

/**
 * Populate Aid Fund Request template with data using config-based approach
 */
async function populateAidFundRequestTemplate(
  worksheet: ExcelJS.Worksheet,
  fundRequest: FundRequestWithDetails
): Promise<void> {
  const config = aidFundRequestConfig;

  // 1. Populate title row (row 4) with format: "FUND Request No: ${fund_request_number} Dated ${date} - ${aid_type} AID"
  const formattedDate = formatDate(fundRequest.created_at);
  const titleText = fundRequest.aid_type
    ? `FUND Request No: ${fundRequest.fund_request_number} Dated ${formattedDate} - ${fundRequest.aid_type} AID`
    : `FUND Request No: ${fundRequest.fund_request_number} Dated ${formattedDate}`;
  
  // Populate row 4 with the title (typically in column A, but could span multiple columns)
  const titleRow = worksheet.getRow(4);
  const titleCell = titleRow.getCell(1); // Column A
  titleCell.value = titleText;

  // 2. Populate fund request number (if different from title row)
  const frNumberCell = worksheet.getCell(config.fundRequestNumber);
  frNumberCell.value = fundRequest.fund_request_number;

  // 2. Clear existing data rows (from data start row to before signature)
  const dataStartRow = config.dataTable.startRow;
  const columns = config.dataTable.columns;
  
  // Find where signature section starts (look for "Prepared by" or similar)
  let signatureStartRow = 0;
  worksheet.eachRow((row, rowNumber) => {
    if (rowNumber >= dataStartRow) {
      const rowText = row.values?.toString().toLowerCase() || '';
      if (rowText.includes('prepared by') || rowText.includes('signature') || rowText.includes('approved by')) {
        signatureStartRow = rowNumber;
        return false; // Stop iteration
      }
    }
  });

  // Clear data rows (keep header row which is dataStartRow - 1)
  const lastDataRow = signatureStartRow > 0 ? signatureStartRow - 1 : dataStartRow + 10; // Fallback
  for (let i = dataStartRow; i <= lastDataRow; i++) {
    const row = worksheet.getRow(i);
    if (row) {
      // Clear only data columns, preserve any formatting
      Object.values(columns).forEach((col) => {
        const cell = row.getCell(col);
        if (cell) {
          cell.value = null;
        }
      });
    }
  }

  // 3. Insert recipient data
  if (fundRequest.recipients && fundRequest.recipients.length > 0) {
    fundRequest.recipients.forEach((recipient, index) => {
      const rowNumber = dataStartRow + index;
      const row = worksheet.getRow(rowNumber);
      
      if (row) {
        row.getCell(columns.slNo).value = index + 1;
        row.getCell(columns.beneficiary).value = getBeneficiaryDisplayValue(recipient);
        row.getCell(columns.nameOfBeneficiary).value = recipient.name_of_beneficiary || recipient.recipient_name || '';
        row.getCell(columns.nameOfInstitution).value = recipient.name_of_institution || '';
        row.getCell(columns.details).value = recipient.details || '';
        row.getCell(columns.fundRequested).value = recipient.fund_requested || 0;
        row.getCell(columns.aadharNo).value = recipient.aadhar_number || '';
        row.getCell(columns.chequeInFavour).value = recipient.cheque_in_favour || '';
        row.getCell(columns.chequeSlNo).value = recipient.cheque_no || '';
      }
    });

    // 4. Update total row
    const totalRowNumber = config.totalRow.row > 0 
      ? config.totalRow.row 
      : dataStartRow + fundRequest.recipients.length;
    
    const totalRow = worksheet.getRow(totalRowNumber);
    if (totalRow) {
      const totalAmount = fundRequest.recipients.reduce((sum, r) => sum + (r.fund_requested || 0), 0);
      totalRow.getCell(config.totalRow.totalLabelColumn).value = 'Total:';
      const totalCell = totalRow.getCell(config.totalRow.totalValueColumn);
      totalCell.value = totalAmount;
      totalCell.numFmt = '#,##0.00';
      totalRow.font = { bold: true };
    }
  }

  // 5. Calculate signature section start row (if dynamic)
  let sigStartRow = config.signatureSection.startRow;
  if (sigStartRow === 0) {
    // Calculate: after total row + 2 blank rows
    const totalRowNum = config.totalRow.row > 0 
      ? config.totalRow.row 
      : dataStartRow + (fundRequest.recipients?.length || 0);
    sigStartRow = totalRowNum + 3;
  }

  // 6. Populate signature section (labels are already in template, we just ensure they exist)
  // Signature section is usually already in template, so we don't need to add it

  // 7. Add cumulative totals section
  if (fundRequest.created_at && fundRequest.id) {
    const previousTotal = await fetchPreviousFundRequestTotal(fundRequest.id, fundRequest.created_at);
    const currentTotal = fundRequest.total_amount || 0;
    const grandTotal = previousTotal + currentTotal;

    // Calculate cumulative section start row
    let cumStartRow = config.cumulativeSection.startRow;
    if (cumStartRow === 0) {
      // Find last row with content, then add 2 blank rows
      let lastContentRow = sigStartRow + 5; // Signature section is usually 5-6 rows
      worksheet.eachRow((row, rowNumber) => {
        if (rowNumber > lastContentRow) {
          const values = row.values;
          if (Array.isArray(values)) {
            const hasContent = values.some((val: any) => val !== null && val !== '') || false;
            if (hasContent) {
              lastContentRow = rowNumber;
            }
          }
        }
      });
      cumStartRow = lastContentRow + 2;
    }

    // Add cumulative totals
    const prevCumRow = worksheet.getRow(cumStartRow);
    prevCumRow.getCell(config.cumulativeSection.previousCumulative.labelCell).value = 'PREVIOUS CUMULATIVE';
    prevCumRow.getCell(config.cumulativeSection.previousCumulative.valueCell).value = previousTotal;
    prevCumRow.getCell(config.cumulativeSection.previousCumulative.valueCell).numFmt = '#,##0.00';
    prevCumRow.font = { bold: true };

    const currentRow = worksheet.getRow(cumStartRow + 1);
    currentRow.getCell(config.cumulativeSection.currentRequest.labelCell).value = 'FUND REQUEST (current)';
    currentRow.getCell(config.cumulativeSection.currentRequest.valueCell).value = currentTotal;
    currentRow.getCell(config.cumulativeSection.currentRequest.valueCell).numFmt = '#,##0.00';
    currentRow.font = { bold: true };

    const totalCumRow = worksheet.getRow(cumStartRow + 2);
    totalCumRow.getCell(config.cumulativeSection.total.labelCell).value = 'TOTAL';
    totalCumRow.getCell(config.cumulativeSection.total.valueCell).value = grandTotal;
    totalCumRow.getCell(config.cumulativeSection.total.valueCell).numFmt = '#,##0.00';
    totalCumRow.font = { bold: true };
    totalCumRow.fill = {
      type: 'pattern',
      pattern: 'solid',
      fgColor: { argb: 'FFE0E0E0' },
    };
  }
}

/**
 * Create Aid Fund Request sheet (fallback when template not available)
 */
async function createAidFundRequestSheet(
  worksheet: ExcelJS.Worksheet,
  fundRequest: FundRequestWithDetails
): Promise<void> {
  // Title row with format: "FUND Request No: ${fund_request_number} Dated ${date} - ${aid_type} AID"
  const formattedDate = formatDate(fundRequest.created_at);
  const titleText = fundRequest.aid_type
    ? `Fund Request No: ${fundRequest.fund_request_number} Dated ${formattedDate} - ${fundRequest.aid_type} Aid`
    : `Fund Request No: ${fundRequest.fund_request_number} Dated ${formattedDate}`;
  
  worksheet.addRow([titleText]);
  worksheet.mergeCells('A1:I1');
  worksheet.getCell('A1').font = { size: 16, bold: true };
  worksheet.getCell('A1').alignment = { horizontal: 'center', vertical: 'middle' };

  // Fund request details
  worksheet.addRow([]);

  // Recipients table
  if (fundRequest.recipients && fundRequest.recipients.length > 0) {
    worksheet.addRow([]);
    
    const headers = [
      'SL No',
      'Beneficiary',
      'Name of beneficiary',
      'Name of Institution',
      'Details',
      'Fund Requested',
      'AAdhar No',
      'Cheque in Favour',
      'Cheque No.',
    ];

    worksheet.addRow(headers);
    const headerRow = worksheet.lastRow;
    if (headerRow) {
      headerRow.font = { bold: true };
      headerRow.fill = {
        type: 'pattern',
        pattern: 'solid',
        fgColor: { argb: 'FFE0E0E0' },
      };
      headerRow.alignment = { horizontal: 'center', vertical: 'middle' };
    }

    // Add recipient data
    fundRequest.recipients.forEach((recipient, index) => {
      worksheet.addRow([
        index + 1,
        getBeneficiaryDisplayValue(recipient),
        recipient.name_of_beneficiary || recipient.recipient_name || '',
        recipient.name_of_institution || '',
        recipient.details || '',
        recipient.fund_requested || 0,
        recipient.aadhar_number || '',
        recipient.cheque_in_favour || '',
        recipient.cheque_no || '',
      ]);
    });

    // Add total row
    const totalRow = worksheet.addRow([
      '',
      '',
      '',
      '',
      'Total:',
      fundRequest.recipients.reduce((sum, r) => sum + (r.fund_requested || 0), 0),
      '',
      '',
      '',
    ]);
    totalRow.font = { bold: true };
    totalRow.getCell(6).alignment = { horizontal: 'right' };

    // Auto-fit columns
    worksheet.columns.forEach((column) => {
      if (column) {
        column.width = 20;
      }
    });
  }

  // Add signature section
  worksheet.addRow([]);
  worksheet.addRow([]);
  worksheet.addRow(['Prepared by:', '', '', '', '', 'Approved by:', '']);
  worksheet.addRow(['', '', '', '', '', '', '']);
  worksheet.addRow(['Signature:', '', '', '', '', 'Signature:', '']);
  worksheet.addRow(['Date:', '', '', '', '', 'Date:', '']);

  // Add cumulative totals
  if (fundRequest.created_at && fundRequest.id) {
    const previousTotal = await fetchPreviousFundRequestTotal(fundRequest.id, fundRequest.created_at);
    const currentTotal = fundRequest.total_amount || 0;
    const grandTotal = previousTotal + currentTotal;

    // Add spacing
    worksheet.addRow([]);
    
    // Add cumulative totals
    const prevCumRow = worksheet.addRow(['PREVIOUS CUMULATIVE', '', '', '', '', previousTotal, '', '', '']);
    prevCumRow.getCell(6).numFmt = '#,##0.00';
    prevCumRow.font = { bold: true };
    
    const currentRow = worksheet.addRow(['FUND REQUEST (current)', '', '', '', '', currentTotal, '', '', '']);
    currentRow.getCell(6).numFmt = '#,##0.00';
    currentRow.font = { bold: true };
    
    const totalRow = worksheet.addRow(['TOTAL', '', '', '', '', grandTotal, '', '', '']);
    totalRow.getCell(6).numFmt = '#,##0.00';
    totalRow.font = { bold: true };
    totalRow.fill = {
      type: 'pattern',
      pattern: 'solid',
      fgColor: { argb: 'FFE0E0E0' },
    };
  }

  // Notes
  if (fundRequest.notes) {
    worksheet.addRow([]);
    worksheet.addRow(['Notes:', fundRequest.notes]);
  }
}

/**
 * Create Article Fund Request sheet
 */
async function createArticleFundRequestSheet(
  worksheet: ExcelJS.Worksheet,
  fundRequest: FundRequestWithDetails
): Promise<void> {
  // Header row
  worksheet.addRow(['FUND REQUEST - ARTICLE']);
  worksheet.mergeCells('A1:J1');
  worksheet.getCell('A1').font = { size: 16, bold: true };
  worksheet.getCell('A1').alignment = { horizontal: 'center', vertical: 'middle' };

  // Fund request details
  worksheet.addRow([]);
  worksheet.addRow(['Fund Request Number:', fundRequest.fund_request_number]);

  // Articles table
  if (fundRequest.articles && fundRequest.articles.length > 0) {
    worksheet.addRow([]);
    
    const headers = [
      'SL.NO',
      'BENEFICIARY',
      'ARTICLE NAME',
      'GST NO.',
      'QTY',
      'PRICE INCLUDING GST',
      'VALUE',
      'CHEQUE IN FAVOUR',
      'CHEQUE NO.',
    ];

    worksheet.addRow(headers);
    const headerRow = worksheet.lastRow;
    if (headerRow) {
      headerRow.font = { bold: true };
      headerRow.fill = {
        type: 'pattern',
        pattern: 'solid',
        fgColor: { argb: 'FFE0E0E0' },
      };
      headerRow.alignment = { horizontal: 'center', vertical: 'middle' };
    }

    // Add article data
    fundRequest.articles.forEach((article) => {
      worksheet.addRow([
        article.sl_no || '',
        'Dist & Public', // Hardcoded beneficiary
        article.article_name,
        fundRequest.gst_number || article.gst_no || '', // Use GST from fund_request
        article.quantity,
        article.price_including_gst,
        article.value,
        article.cheque_in_favour || '',
        article.cheque_no || '',
      ]);
    });

    // Add total row
    const totalRow = worksheet.addRow([
      '',
      '',
      'Total:',
      '',
      '',
      '',
      fundRequest.articles.reduce((sum, a) => sum + (a.value || 0), 0),
      '',
      '',
    ]);
    totalRow.font = { bold: true };
    totalRow.getCell(7).alignment = { horizontal: 'right' };

    // Auto-fit columns
    worksheet.columns.forEach((column) => {
      if (column) {
        column.width = 20;
      }
    });
  }

  // Add signature section
  worksheet.addRow([]);
  worksheet.addRow([]);
  worksheet.addRow(['Prepared by:', '', '', '', '', 'Approved by:', '']);
  worksheet.addRow(['', '', '', '', '', '', '']);
  worksheet.addRow(['Signature:', '', '', '', '', 'Signature:', '']);
  worksheet.addRow(['Date:', '', '', '', '', 'Date:', '']);

  // Notes
  if (fundRequest.notes) {
    worksheet.addRow([]);
    worksheet.addRow(['Notes:', fundRequest.notes]);
  }
}

/**
 * Store document metadata
 */
export const storeDocumentMetadata = async (
  fundRequestId: string,
  documentType: 'fund_request' | 'purchase_order',
  fileName: string,
  filePath?: string
): Promise<void> => {
  try {
    const { data: { session } } = await supabase.auth.getSession();
    const userId = session?.user?.id || null;

    const { error } = await supabase
      .from('fund_request_documents')
      .insert([{
        fund_request_id: fundRequestId,
        document_type: documentType,
        file_name: fileName,
        file_path: filePath,
        generated_by: userId,
      }]);

    if (error) {
      console.error('Error storing document metadata:', error);
      throw error;
    }
  } catch (error) {
    console.error('Failed to store document metadata:', error);
    throw error;
  }
};

/**
 * Format date to DD-MM-YY format for Purchase Order
 */
const formatPODate = (): string => {
  const date = new Date();
  const day = date.getDate().toString().padStart(2, '0');
  const month = (date.getMonth() + 1).toString().padStart(2, '0');
  const year = date.getFullYear().toString().slice(-2);
  return `${day}-${month}-${year}`;
};

/**
 * Generate Purchase Order document for Article fund requests
 */
export const generatePurchaseOrderDocument = async (fundRequestId: string): Promise<Blob> => {
  try {
    let fundRequest = await fetchFundRequestById(fundRequestId);
    if (!fundRequest) {
      throw new Error('Fund request not found');
    }

    if (fundRequest.fund_request_type !== 'Article') {
      throw new Error('Purchase Order can only be generated for Article type fund requests');
    }

    if (!fundRequest.articles || fundRequest.articles.length === 0) {
      throw new Error('No articles found in fund request');
    }

    // Generate and store purchase order number if it doesn't exist
    let purchaseOrderNumber = fundRequest.purchase_order_number;
    if (!purchaseOrderNumber) {
      purchaseOrderNumber = await generatePurchaseOrderNumber();
      // Update the fund request with the PO number
      const { error: updateError } = await supabase
        .from('fund_request')
        .update({ purchase_order_number: purchaseOrderNumber })
        .eq('id', fundRequestId);
      
      if (updateError) {
        console.error('Error updating purchase order number:', updateError);
        // Continue anyway - we'll use the generated number for the document
      } else {
        // Update the local object
        fundRequest = { ...fundRequest, purchase_order_number: purchaseOrderNumber };
      }
    }

    const workbook = new ExcelJS.Workbook();
    const worksheet = workbook.addWorksheet('Purchase Order');
    
    const currentDate = formatPODate();
    const totalAmount = (fundRequest.articles || []).reduce((sum, a) => sum + (a.value || 0), 0);

    // Set row heights for logo section (rows 1-2, each 30)
    worksheet.getRow(1).height = 30;
    worksheet.getRow(2).height = 30;

    // Try to add logo image
    // Note: ExcelJS doesn't support WebP directly, so we'll skip the logo in XLSX for now
    // The logo will be included in the PDF version
    // If needed, convert logo.webp to PNG/JPEG for XLSX support

    // Company information below logo (rows 3-7)
    worksheet.getRow(3).getCell(1).value = 'Melmaruvathur Adhiparasakthi Spiritual Movement';
    worksheet.getRow(4).getCell(1).value = 'GST Road, Melmaruvathur 603319';
    worksheet.getRow(5).getCell(1).value = 'Chengalpet District, Tamilnadu';
    worksheet.getRow(6).getCell(1).value = 'GST NO: 33AACTM0073D1Z5.';
    worksheet.getRow(7).getCell(1).value = 'Website: maruvoorhelp@gmail.com';

    // Style company info
    for (let i = 3; i <= 7; i++) {
      const cell = worksheet.getRow(i).getCell(1);
      cell.font = { size: 9 };
    }

    // "PURCHASE ORDER" text on right (rows 1-2, columns E-F)
    const poCell = worksheet.getRow(1).getCell(5);
    poCell.value = 'PURCHASE ORDER';
    poCell.font = { size: 20, bold: true, color: { argb: 'FF008000' } };
    poCell.alignment = { vertical: 'middle', horizontal: 'center' };
    worksheet.mergeCells('E1:F1');

    // Purchase Order Number and Date below "PURCHASE ORDER" (row 3)
    const poNumberLabelCell = worksheet.getRow(3).getCell(5);
    poNumberLabelCell.value = 'PO NO';
    poNumberLabelCell.font = { size: 10, bold: true };
    const poNumberValueCell = worksheet.getRow(3).getCell(6);
    poNumberValueCell.value = purchaseOrderNumber || '';
    poNumberValueCell.font = { size: 10 };
    
    // Date (row 4)
    const dateLabelCell = worksheet.getRow(4).getCell(5);
    dateLabelCell.value = 'DATE';
    dateLabelCell.font = { size: 10, bold: true };
    const dateValueCell = worksheet.getRow(4).getCell(6);
    dateValueCell.value = currentDate;
    dateValueCell.font = { size: 10 };

    // Empty row
    worksheet.addRow([]);
    let currentRow = 9;

    // Vendor Section (left side)
    const vendorHeaderRow = worksheet.getRow(currentRow);
    vendorHeaderRow.getCell(1).value = 'VENDOR';
    vendorHeaderRow.getCell(1).font = { size: 10, bold: true, color: { argb: 'FFFFFFFF' } };
    vendorHeaderRow.getCell(1).fill = {
      type: 'pattern',
      pattern: 'solid',
      fgColor: { argb: 'FF008000' },
    };
    vendorHeaderRow.getCell(1).alignment = { vertical: 'middle' };
    worksheet.mergeCells(`A${currentRow}:B${currentRow}`);
    currentRow++;

    // Vendor details
    worksheet.getRow(currentRow++).getCell(1).value = fundRequest.supplier_name || '';
    worksheet.getRow(currentRow++).getCell(1).value = fundRequest.gst_number || '';
    worksheet.getRow(currentRow++).getCell(1).value = fundRequest.supplier_address || '';
    const cityStatePincode = [fundRequest.supplier_city, fundRequest.supplier_state, fundRequest.supplier_pincode]
      .filter(Boolean)
      .join(', ');
    worksheet.getRow(currentRow++).getCell(1).value = cityStatePincode;

    // Ship To Section (right side, same rows)
    const shipToStartRow = 9;
    const shipToHeaderRow = worksheet.getRow(shipToStartRow);
    shipToHeaderRow.getCell(4).value = 'SHIP TO';
    shipToHeaderRow.getCell(4).font = { size: 10, bold: true, color: { argb: 'FFFFFFFF' } };
    shipToHeaderRow.getCell(4).fill = {
      type: 'pattern',
      pattern: 'solid',
      fgColor: { argb: 'FF008000' },
    };
    shipToHeaderRow.getCell(4).alignment = { vertical: 'middle' };
    worksheet.mergeCells(`D${shipToStartRow}:E${shipToStartRow}`);

    let shipToRow = shipToStartRow + 1;
    worksheet.getRow(shipToRow++).getCell(4).value = 'Melmaruvathur Adhiparasakthi Spiritual Movement';
    worksheet.getRow(shipToRow++).getCell(4).value = 'GST Road, Melmaruvathur 603319';
    worksheet.getRow(shipToRow++).getCell(4).value = 'Chengalpet District, Tamilnadu';

    // Style vendor and ship-to content
    for (let i = shipToStartRow + 1; i <= shipToStartRow + 4; i++) {
      const vendorCell = worksheet.getRow(i).getCell(1);
      const shipToCell = worksheet.getRow(i).getCell(4);
      if (vendorCell.value) vendorCell.font = { size: 9 };
      if (shipToCell.value) shipToCell.font = { size: 9 };
    }

    // Empty rows (2-3 rows)
    currentRow += 2;
    worksheet.addRow([]);
    worksheet.addRow([]);
    currentRow += 2;

    // Item Table Headers
    const headerRow = worksheet.getRow(currentRow);
    headerRow.getCell(1).value = 'ITEM NAME';
    headerRow.getCell(2).value = 'DESCRIPTION';
    headerRow.getCell(3).value = 'QTY';
    headerRow.getCell(4).value = 'UNIT PRICE';
    headerRow.getCell(5).value = 'TOTAL\n(Inclusive of Tax)';

    // Style header row
    for (let col = 1; col <= 5; col++) {
      const cell = headerRow.getCell(col);
      cell.font = { size: 10, bold: true, color: { argb: 'FFFFFFFF' } };
      cell.fill = {
        type: 'pattern',
        pattern: 'solid',
        fgColor: { argb: 'FF008000' },
      };
      cell.alignment = { 
        vertical: 'middle', 
        horizontal: col === 4 || col === 5 ? 'right' : 'center',
        wrapText: col === 5 // Enable text wrapping for TOTAL column
      };
      cell.border = {
        top: { style: 'thin' },
        left: { style: 'thin' },
        bottom: { style: 'thin' },
        right: { style: 'thin' },
      };
    }
    currentRow++;

    // Article data rows
    (fundRequest.articles || []).forEach((article) => {
      const row = worksheet.getRow(currentRow);
      row.getCell(1).value = article.supplier_article_name || article.article_name || '';
      row.getCell(2).value = article.description || ''; // Description
      row.getCell(3).value = article.quantity || 0;
      row.getCell(4).value = article.price_including_gst || 0;
      row.getCell(5).value = article.value || 0;

      // Style data row
      for (let col = 1; col <= 5; col++) {
        const cell = row.getCell(col);
        cell.font = { size: 9 };
        cell.alignment = { 
          vertical: 'middle', 
          horizontal: col === 4 || col === 5 ? 'right' : 'left' 
        };
        cell.border = {
          top: { style: 'thin' },
          left: { style: 'thin' },
          bottom: { style: 'thin' },
          right: { style: 'thin' },
        };
        if (col === 4 || col === 5) {
          cell.numFmt = '#,##0.00';
        }
      }
      currentRow++;
    });

    // Total row
    const totalRow = worksheet.getRow(currentRow);
    totalRow.getCell(4).value = 'TOTAL\n(Inclusive of Tax)';
    totalRow.getCell(4).font = { size: 10, bold: true };
    totalRow.getCell(4).alignment = { horizontal: 'right', vertical: 'middle', wrapText: true };
    totalRow.getCell(5).value = totalAmount;
    totalRow.getCell(5).font = { size: 10, bold: true };
    totalRow.getCell(5).numFmt = '₹ #,##0.00';
    totalRow.getCell(5).alignment = { horizontal: 'right' };
    totalRow.getCell(5).fill = {
      type: 'pattern',
      pattern: 'solid',
      fgColor: { argb: 'FFF5F5F5' },
    };
    currentRow++;

    // Empty row
    currentRow++;
    worksheet.addRow([]);

    // Comments Section
    const commentsHeaderRow = worksheet.getRow(currentRow);
    commentsHeaderRow.getCell(1).value = 'Comments or Special Instructions';
    commentsHeaderRow.getCell(1).font = { size: 10, bold: true, color: { argb: 'FFFFFFFF' } };
    commentsHeaderRow.getCell(1).fill = {
      type: 'pattern',
      pattern: 'solid',
      fgColor: { argb: 'FF008000' },
    };
    commentsHeaderRow.getCell(1).alignment = { vertical: 'middle' };
    worksheet.mergeCells(`A${currentRow}:B${currentRow}`);
    currentRow++;

    // Empty rows for comments (4-5 rows)
    for (let i = 0; i < 5; i++) {
      const row = worksheet.getRow(currentRow + i);
      row.getCell(1).border = {
        top: { style: 'dashed' },
        left: { style: 'dashed' },
        bottom: { style: 'dashed' },
        right: { style: 'dashed' },
      };
      worksheet.mergeCells(`A${currentRow + i}:B${currentRow + i}`);
      row.height = 15;
    }
    currentRow += 5;

    // Footer - Contact information (centered, last 2 rows)
    const footerRow1 = worksheet.getRow(currentRow);
    footerRow1.getCell(1).value = 'If you have any questions about this purchase order, please contact';
    footerRow1.getCell(1).font = { size: 9 };
    footerRow1.getCell(1).alignment = { horizontal: 'center' };
    worksheet.mergeCells(`A${currentRow}:E${currentRow}`);
    currentRow++;

    const footerRow2 = worksheet.getRow(currentRow);
    footerRow2.getCell(1).value = 'R.Surendranath, +91 98400 46263, maruvoorhelp@gmail.com';
    footerRow2.getCell(1).font = { size: 9 };
    footerRow2.getCell(1).alignment = { horizontal: 'center' };
    worksheet.mergeCells(`A${currentRow}:E${currentRow}`);

    // Set column widths
    worksheet.getColumn(1).width = 25; // ITEM NAME
    worksheet.getColumn(2).width = 25; // DESCRIPTION
    worksheet.getColumn(3).width = 10; // QTY
    worksheet.getColumn(4).width = 15; // UNIT PRICE
    worksheet.getColumn(5).width = 15; // TOTAL

    // Generate buffer
    const buffer = await workbook.xlsx.writeBuffer();
    return new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
  } catch (error) {
    console.error('Error generating purchase order document:', error);
    throw error;
  }
};

/**
 * Load logo images and convert to data URIs
 * Returns both current logo (for right side) and guru logo (for left side)
 */
const loadLogosAsDataUri = async (): Promise<{
  currentLogo: string | null;
  guruLogo: string | null;
  signature: string | null;
}> => {
  const loadImageAsDataUri = async (url: string): Promise<string | null> => {
    try {
      const response = await fetch(url);
      if (response.ok) {
        const blob = await response.blob();
        return new Promise((resolve) => {
          const reader = new FileReader();
          reader.onloadend = () => {
            resolve(reader.result as string);
          };
          reader.onerror = () => {
            resolve(null);
          };
          reader.readAsDataURL(blob);
        });
      }
    } catch (error) {
      console.warn(`Could not load image from ${url}:`, error);
    }
    return null;
  };

  // Load current logo (logo.png) - for right side
  let currentLogo: string | null = null;
  try {
    // Try public folder first
    currentLogo = await loadImageAsDataUri('/model-docs/logo.png');
    if (!currentLogo) {
      // Fallback: try src folder (for development)
      currentLogo = await loadImageAsDataUri('/src/model-docs/logo.png');
    }
  } catch (error) {
    console.warn('Could not load current logo:', error);
  }

  // Load guru logo (guru-logo.jpg) - for left side
  let guruLogo: string | null = null;
  try {
    // Try using imported path first (works in both dev and production)
    if (guruLogoPath) {
      guruLogo = await loadImageAsDataUri(guruLogoPath);
    }
    if (!guruLogo) {
      // Fallback: try assets folder path
      guruLogo = await loadImageAsDataUri('/src/assets/guru-logo.jpg');
    }
    if (!guruLogo) {
      // Fallback: try public folder
      guruLogo = await loadImageAsDataUri('/guru-logo.jpg');
    }
  } catch (error) {
    console.warn('Could not load guru logo:', error);
  }

  // Load signature image (sign.jpg) - for "FOR MASM" section
  let signature: string | null = null;
  try {
    if (signaturePath) {
      signature = await loadImageAsDataUri(signaturePath);
    }
    if (!signature) {
      signature = await loadImageAsDataUri('/src/assets/sign.jpg');
    }
    if (!signature) {
      signature = await loadImageAsDataUri('/sign.jpg');
    }
  } catch (error) {
    console.warn('Could not load signature image:', error);
  }

  return { currentLogo, guruLogo, signature };
};

/**
 * Generate Purchase Order PDF document for Article fund requests
 */
export const generatePurchaseOrderPDF = async (fundRequestId: string): Promise<Blob> => {
  // Generate and store purchase order number if it doesn't exist
  let fundRequest = await fetchFundRequestById(fundRequestId);
  if (!fundRequest) {
    throw new Error('Fund request not found');
  }

  if (!fundRequest.purchase_order_number) {
    const purchaseOrderNumber = await generatePurchaseOrderNumber();
    // Update the fund request with the PO number
    const { error: updateError } = await supabase
      .from('fund_request')
      .update({ purchase_order_number: purchaseOrderNumber })
      .eq('id', fundRequestId);
    
    if (updateError) {
      console.error('Error updating purchase order number:', updateError);
      // Continue anyway - we'll use the generated number for the document
    } else {
      // Update the local object
      fundRequest = { ...fundRequest, purchase_order_number: purchaseOrderNumber };
    }
  }

  // Continue with existing PDF generation logic
  try {
    if (fundRequest.fund_request_type !== 'Article') {
      throw new Error('Purchase Order can only be generated for Article type fund requests');
    }

    if (!fundRequest.articles || fundRequest.articles.length === 0) {
      throw new Error('No articles found in fund request');
    }

    // Load logos as data URIs
    const { currentLogo, guruLogo, signature } = await loadLogosAsDataUri();

    // Generate PDF using React PDF
    const pdfDoc = React.createElement(PurchaseOrderPDFDocument, {
      fundRequest,
      logoDataUri: currentLogo,
      guruLogoDataUri: guruLogo,
      signatureDataUri: signature,
    }) as React.ReactElement;

    // Generate PDF blob
    const pdfBlob = await pdf(pdfDoc).toBlob();
    return pdfBlob;
  } catch (error) {
    console.error('Error generating purchase order PDF:', error);
    throw error;
  }
};
