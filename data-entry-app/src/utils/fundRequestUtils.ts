import type { FundRequestRecipient } from '../services/fundRequestService';

/**
 * Format beneficiary types from recipients into a readable string
 * Examples:
 * - Single type: "District"
 * - Two types: "District & Public"
 * - Three+ types: "District, Public & Institutions"
 */
export function formatBeneficiaryTypes(recipients: FundRequestRecipient[]): string {
  const types = new Set(
    recipients
      .map((r) => r.beneficiary_type)
      .filter((type): type is 'District' | 'Public' | 'Institutions' | 'Others' => Boolean(type))
  );
  const typeArray = Array.from(types);
  
  if (typeArray.length === 0) return '';
  if (typeArray.length === 1) return typeArray[0]!;
  if (typeArray.length === 2) return `${typeArray[0]} & ${typeArray[1]}`;
  
  // Three or more types
  const lastType = typeArray[typeArray.length - 1];
  const otherTypes = typeArray.slice(0, -1).join(', ');
  return `${otherTypes} & ${lastType}`;
}

/**
 * Format date string to DD-MM-YYYY format
 */
export function formatDate(dateString: string | undefined): string {
  if (!dateString) return '';
  const date = new Date(dateString);
  const day = date.getDate().toString().padStart(2, '0');
  const month = (date.getMonth() + 1).toString().padStart(2, '0');
  const year = date.getFullYear();
  return `${day}-${month}-${year}`;
}

/**
 * Get the correct beneficiary display value based on beneficiary type
 * - For District type: Use district_name if available, otherwise extract from beneficiary string
 * - For Public/Institutions/Others type: Extract application number (before first '-')
 * - For other types: Return the beneficiary field as-is
 */
export function getBeneficiaryDisplayValue(recipient: FundRequestRecipient): string {
  if (!recipient.beneficiary) return '';
  
  if (recipient.beneficiary_type === 'District') {
    // Use district_name if available (preferred)
    if (recipient.district_name) {
      return recipient.district_name;
    }
    // Fallback: Extract district name (between first and second '-')
    // Format: "D XXX - DistrictName - ₹ amount"
    const parts = recipient.beneficiary.split(' - ');
    return parts.length >= 2 ? parts[1] : recipient.beneficiary;
  } else if (
    recipient.beneficiary_type === 'Public' ||
    recipient.beneficiary_type === 'Institutions' ||
    recipient.beneficiary_type === 'Others'
  ) {
    // Extract application number (before first '-')
    // Format: "P/I/O XXX - ... - ₹ amount"
    const parts = recipient.beneficiary.split(' - ');
    return parts.length >= 1 ? parts[0].trim() : recipient.beneficiary;
  }
  
  return recipient.beneficiary;
}

/**
 * Get beneficiary display value for export
 * - For Article: return "All Districts & Public"
 * - For Aid District: use district_name if available, otherwise extract from beneficiary
 * - For Aid Public/Institutions/Others: extract application number (before first '-')
 */
export function getBeneficiaryDisplayValueForExport(
  recipient: FundRequestRecipient | null,
  fundRequestType: 'Aid' | 'Article'
): string {
  if (fundRequestType === 'Article') {
    return 'All Districts & Public';
  }
  
  if (!recipient) return '';
  
  if (recipient.beneficiary_type === 'District') {
    // Use district_name if available (preferred)
    if (recipient.district_name) {
      return recipient.district_name;
    }
    // Fallback: Extract district name (between first and second '-')
    if (recipient.beneficiary) {
      const parts = recipient.beneficiary.split(' - ');
      return parts.length >= 2 ? parts[1] : recipient.beneficiary;
    }
    return '';
  } else if (recipient.beneficiary_type === 'Public' || 
             recipient.beneficiary_type === 'Institutions' || 
             recipient.beneficiary_type === 'Others') {
    // Extract application number (before first '-')
    if (recipient.beneficiary) {
      const parts = recipient.beneficiary.split(' - ');
      return parts.length >= 1 ? parts[0].trim() : recipient.beneficiary;
    }
    return '';
  }
  
  return recipient.beneficiary || '';
}
