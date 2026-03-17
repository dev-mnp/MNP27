/**
 * Excel Template Configuration
 * This file defines cell positions for the Fund Request Excel template.
 * Update these values when the template design changes - no code changes needed!
 */

export interface ExcelTemplateConfig {
  // Fund request number cell (e.g., "B2")
  fundRequestNumber: string;
  
  // Data table configuration
  dataTable: {
    startRow: number; // Row where data starts (after header row)
    columns: {
      slNo: string; // Column letter, e.g., "A"
      beneficiary: string;
      nameOfBeneficiary: string;
      nameOfInstitution: string;
      details: string;
      fundRequested: string;
      aadharNo: string;
      chequeInFavour: string;
      chequeSlNo: string;
    };
  };
  
  // Total row (after data rows)
  totalRow: {
    row: number; // Row number (0 means calculate dynamically)
    totalLabelColumn: string; // Column where "Total:" label is
    totalValueColumn: string; // Column where total amount is
  };
  
  // Signature section
  signatureSection: {
    startRow: number; // Row where signature section starts
    preparedBy: {
      labelCell: string; // e.g., "A20"
      signatureCell: string; // e.g., "A21"
      dateCell: string; // e.g., "A22"
    };
    approvedBy: {
      labelCell: string; // e.g., "F20"
      signatureCell: string; // e.g., "F21"
      dateCell: string; // e.g., "F22"
    };
  };
  
  // Cumulative totals section (after signature)
  cumulativeSection: {
    startRow: number; // Row where cumulative section starts
    previousCumulative: {
      labelCell: string; // e.g., "A25"
      valueCell: string; // e.g., "F25"
    };
    currentRequest: {
      labelCell: string; // e.g., "A26"
      valueCell: string; // e.g., "F26"
    };
    total: {
      labelCell: string; // e.g., "A27"
      valueCell: string; // e.g., "F27"
    };
  };
}

/**
 * Configuration for Aid Fund Request template
 * Update these values based on your actual template layout
 */
export const aidFundRequestConfig: ExcelTemplateConfig = {
  fundRequestNumber: 'B2', // Adjust based on your template
  
  dataTable: {
    startRow: 5, // Row 5 is where data starts (row 4 is header)
    columns: {
      slNo: 'A',
      beneficiary: 'B',
      nameOfBeneficiary: 'C',
      nameOfInstitution: 'D',
      details: 'E',
      fundRequested: 'F',
      aadharNo: 'G',
      chequeInFavour: 'H',
      chequeSlNo: 'I',
    },
  },
  
  totalRow: {
    row: 0, // 0 means calculate dynamically: dataStartRow + recipientCount
    totalLabelColumn: 'E',
    totalValueColumn: 'F',
  },
  
  signatureSection: {
    startRow: 0, // 0 means calculate dynamically: after total row + 2 blank rows
    preparedBy: {
      labelCell: 'A', // Will be combined with row number
      signatureCell: 'A', // Will be combined with row number
      dateCell: 'A', // Will be combined with row number
    },
    approvedBy: {
      labelCell: 'F', // Will be combined with row number
      signatureCell: 'F', // Will be combined with row number
      dateCell: 'F', // Will be combined with row number
    },
  },
  
  cumulativeSection: {
    startRow: 0, // 0 means calculate dynamically: after signature section + 1 blank row
    previousCumulative: {
      labelCell: 'A',
      valueCell: 'F',
    },
    currentRequest: {
      labelCell: 'A',
      valueCell: 'F',
    },
    total: {
      labelCell: 'A',
      valueCell: 'F',
    },
  },
};

/**
 * Helper function to get cell address from column and row
 */
export function getCellAddress(column: string, row: number): string {
  return `${column}${row}`;
}

/**
 * Helper function to parse cell address to column and row
 */
export function parseCellAddress(cell: string): { column: string; row: number } {
  const match = cell.match(/^([A-Z]+)(\d+)$/);
  if (!match) {
    throw new Error(`Invalid cell address: ${cell}`);
  }
  return {
    column: match[1],
    row: parseInt(match[2], 10),
  };
}

