import { supabase } from '../lib/supabase';
import type { MasterEntryRecord, ArticleSelection } from '../data/mockData';
import { logAction } from './auditLogService';

export interface InstitutionBeneficiaryEntry {
  id?: string;
  institution_name: string;
  institution_type: 'institutions' | 'others';
  application_number?: string;
  address?: string | null;
  mobile?: string | null;
  article_id: string;
  quantity: number;
  article_cost_per_unit?: number | null;
  total_amount: number;
  notes?: string | null;
  status?: 'pending' | 'approved' | 'rejected' | 'completed';
  created_at?: string;
  updated_at?: string;
  created_by?: string;
}

export interface InstitutionBeneficiaryEntryWithJoins extends InstitutionBeneficiaryEntry {
  articles?: {
    article_name: string;
    cost_per_unit: number;
  };
}

/**
 * Get current user ID from session
 */
const getCurrentUserId = async (): Promise<string | null> => {
  try {
    const { data: { session } } = await supabase.auth.getSession();
    return session?.user?.id || null;
  } catch {
    return null;
  }
};

/**
 * Create institution beneficiary entries
 * For institution type, we create one entry per article
 */
export const createInstitutionBeneficiaryEntries = async (
  entries: Omit<InstitutionBeneficiaryEntry, 'id' | 'created_at' | 'updated_at'>[]
): Promise<InstitutionBeneficiaryEntry[]> => {
  try {
    const { data, error } = await supabase
      .from('institutions_beneficiary_entries')
      .insert(entries)
      .select();

    if (error) {
      console.error('Error creating institution beneficiary entries:', error);
      throw error;
    }

    const result = data || [];

    // Log audit action with new values
    if (result.length > 0) {
      const userId = await getCurrentUserId();
      const applicationNumber = result[0].application_number;
      await logAction(userId, 'CREATE', 'institution_beneficiary', applicationNumber || null, {
        entity_name: applicationNumber,
        entity_summary: `Institution Beneficiary Entry: ${applicationNumber}`,
        new_values: {
          application_number: applicationNumber,
          institution_name: result[0].institution_name,
          institution_type: result[0].institution_type,
          entries_count: result.length,
          entries: result.map((entry) => ({
            article_id: entry.article_id,
            quantity: entry.quantity,
            total_amount: entry.total_amount,
          })),
        },
      });
    }

    return result;
  } catch (error) {
    console.error('Failed to create institution beneficiary entries:', error);
    throw error;
  }
};

/**
 * Fetch institution beneficiary entries
 */
export const fetchInstitutionBeneficiaryEntries = async (
  institutionName?: string
): Promise<InstitutionBeneficiaryEntry[]> => {
  try {
    let query = supabase
      .from('institutions_beneficiary_entries')
      .select('*')
      .order('created_at', { ascending: false });

    if (institutionName) {
      query = query.eq('institution_name', institutionName);
    }

    const { data, error } = await query;

    if (error) {
      console.error('Error fetching institution beneficiary entries:', error);
      throw error;
    }

    return data || [];
  } catch (error) {
    console.error('Failed to fetch institution beneficiary entries:', error);
    throw error;
  }
};

/**
 * Fetch institution beneficiary entries grouped by application number
 * Returns records in MasterEntryRecord format for display
 */
export const fetchInstitutionBeneficiaryEntriesGrouped = async (): Promise<MasterEntryRecord[]> => {
  try {
    const { data, error } = await supabase
      .from('institutions_beneficiary_entries')
      .select(`
        *,
        articles:article_id (
          article_name,
          cost_per_unit
        )
      `)
      .order('application_number', { ascending: false })
      .order('created_at', { ascending: false });

    if (error) {
      console.error('Error fetching institution beneficiary entries:', error);
      throw error;
    }

    if (!data || data.length === 0) {
      return [];
    }

    // Group entries by application_number
    const groupedByAppNumber = new Map<string, any[]>();

    data.forEach((entry: any) => {
      const appNumber = entry.application_number;
      if (!appNumber) return; // Skip entries without application number

      if (!groupedByAppNumber.has(appNumber)) {
        groupedByAppNumber.set(appNumber, []);
      }
      groupedByAppNumber.get(appNumber)!.push(entry);
    });

    // Transform grouped data to MasterEntryRecord format
    const records: MasterEntryRecord[] = [];

    groupedByAppNumber.forEach((entries, applicationNumber) => {
      if (entries.length === 0) return;

      const firstEntry = entries[0];
      const institutionName = firstEntry.institution_name || '';
      const institutionType = firstEntry.institution_type || 'institutions';

      // Transform entries to ArticleSelection array
      const selectedArticles: ArticleSelection[] = entries.map((entry: any) => ({
        articleId: entry.article_id,
        articleName: entry.articles?.article_name || '',
        quantity: entry.quantity,
        costPerUnit: entry.article_cost_per_unit != null 
          ? parseFloat(entry.article_cost_per_unit) 
          : parseFloat(entry.articles?.cost_per_unit || 0),
        totalValue: parseFloat(entry.total_amount || 0),
        comments: entry.notes || '',
      }));

      // Calculate total accrued for this application
      const totalAccrued = entries.reduce(
        (sum, entry) => sum + parseFloat(entry.total_amount || 0),
        0
      );

      // Get earliest created_at
      const createdAt = entries.reduce((earliest, entry) => {
        const entryDate = entry.created_at ? new Date(entry.created_at).getTime() : 0;
        const earliestDate = earliest ? new Date(earliest).getTime() : Infinity;
        return entryDate < earliestDate ? entry.created_at : earliest;
      }, entries[0]?.created_at || new Date().toISOString());

      const record: MasterEntryRecord = {
        id: firstEntry.id || applicationNumber,
        applicationNumber: applicationNumber,
        beneficiaryType: 'institutions',
        institutionName: institutionName,
        institutionType: institutionType as 'institutions' | 'others',
        address: firstEntry.address || undefined,
        mobile: firstEntry.mobile || undefined,
        selectedArticles: selectedArticles,
        totalAccrued: totalAccrued,
        createdAt: createdAt,
      };

      records.push(record);
    });

    // Sort by created_at descending (newest first)
    records.sort((a, b) => {
      const dateA = new Date(a.createdAt).getTime();
      const dateB = new Date(b.createdAt).getTime();
      return dateB - dateA;
    });

    return records;
  } catch (error) {
    console.error('Failed to fetch and group institution beneficiary entries:', error);
    throw error;
  }
};

/**
 * Delete institution beneficiary entry
 */
export const deleteInstitutionBeneficiaryEntry = async (id: string): Promise<void> => {
  try {
    // Get entry details before deletion for audit log
    const { data: entryData } = await supabase
      .from('institutions_beneficiary_entries')
      .select('application_number, institution_name')
      .eq('id', id)
      .single();

    const { error } = await supabase
      .from('institutions_beneficiary_entries')
      .delete()
      .eq('id', id);

    if (error) {
      console.error('Error deleting institution beneficiary entry:', error);
      throw error;
    }

    // Log audit action with deleted values
    const userId = await getCurrentUserId();
    await logAction(userId, 'DELETE', 'institution_beneficiary', entryData?.application_number || id, {
      entity_name: entryData?.application_number || id,
      entity_summary: `Institution Beneficiary Entry: ${entryData?.application_number || id}`,
      deleted_values: entryData ? {
        entry_id: id,
        application_number: entryData.application_number,
        institution_name: entryData.institution_name,
      } : {},
    });
  } catch (error) {
    console.error('Failed to delete institution beneficiary entry:', error);
    throw error;
  }
};

/**
 * Delete all entries for an application number
 */
export const deleteInstitutionBeneficiaryEntriesByApplicationNumber = async (
  applicationNumber: string
): Promise<void> => {
  try {
    // Get entry count before deletion for audit log
    const { count } = await supabase
      .from('institutions_beneficiary_entries')
      .select('*', { count: 'exact', head: true })
      .eq('application_number', applicationNumber);

    const { error } = await supabase
      .from('institutions_beneficiary_entries')
      .delete()
      .eq('application_number', applicationNumber);

    if (error) {
      console.error('Error deleting institution beneficiary entries by application number:', error);
      throw error;
    }

    // Log audit action with deleted values
    const userId = await getCurrentUserId();
    await logAction(userId, 'DELETE', 'institution_beneficiary', applicationNumber, {
      entity_name: applicationNumber,
      entity_summary: `Institution Beneficiary Entry: ${applicationNumber}`,
      deleted_values: {
        application_number: applicationNumber,
        entries_deleted: count || 0,
      },
    });
  } catch (error) {
    console.error('Failed to delete institution beneficiary entries by application number:', error);
    throw error;
  }
};
