/**
 * CSV Export Utility
 * Converts data arrays to CSV format and triggers browser download
 */

/**
 * Escape CSV field value
 */
const escapeCSVField = (value: any): string => {
  if (value === null || value === undefined) {
    return '';
  }

  const stringValue = String(value);
  
  // If the value contains comma, newline, or double quote, wrap it in quotes and escape quotes
  if (stringValue.includes(',') || stringValue.includes('\n') || stringValue.includes('"')) {
    return `"${stringValue.replace(/"/g, '""')}"`;
  }
  
  return stringValue;
};

/**
 * Convert array of objects to CSV string
 */
export const convertToCSV = (data: Record<string, any>[], headers?: string[]): string => {
  if (!data || data.length === 0) {
    return '';
  }

  // If headers not provided, use keys from first object
  const csvHeaders = headers || Object.keys(data[0]);

  // Create header row
  const headerRow = csvHeaders.map(escapeCSVField).join(',');

  // Create data rows
  const dataRows = data.map((row) => {
    return csvHeaders.map((header) => {
      // Handle nested objects (e.g., articles.article_name)
      const value = header.includes('.')
        ? header.split('.').reduce((obj: any, key: string) => obj?.[key], row)
        : row[header];
      return escapeCSVField(value);
    }).join(',');
  });

  // Combine header and data rows
  return [headerRow, ...dataRows].join('\n');
};

/**
 * Trigger browser download of CSV file
 */
export const downloadCSV = (csvContent: string, filename: string): void => {
  // Add BOM for UTF-8 to ensure Excel opens it correctly
  const BOM = '\uFEFF';
  const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);

  link.setAttribute('href', url);
  link.setAttribute('download', filename);
  link.style.visibility = 'hidden';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

/**
 * Export data array to CSV file
 * @param data - Array of objects to export
 * @param filename - Name of the file (without .csv extension)
 * @param headers - Optional array of header names. If not provided, uses object keys from first item.
 *                  Can use dot notation for nested properties (e.g., 'articles.article_name')
 * @param onError - Optional callback for error notifications (replaces alert)
 */
export const exportToCSV = (
  data: Record<string, any>[],
  filename: string,
  headers?: string[],
  onError?: (message: string) => void
): void => {
  if (!data || data.length === 0) {
    const errorMessage = 'No data to export';
    if (onError) {
      onError(errorMessage);
    } else {
      console.warn(errorMessage);
    }
    return;
  }

  try {
    const csvContent = convertToCSV(data, headers);
    const timestamp = new Date().toISOString().split('T')[0];
    const fullFilename = `${filename}-${timestamp}.csv`;
    downloadCSV(csvContent, fullFilename);
  } catch (error) {
    console.error('Error exporting to CSV:', error);
    const errorMessage = 'Failed to export data. Please try again.';
    if (onError) {
      onError(errorMessage);
    } else {
      console.error(errorMessage);
    }
  }
};
