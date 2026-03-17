import { supabase } from '../lib/supabase';
import { logAction } from './auditLogService';
import { fetchAllArticles } from './articlesService';

export interface FundRequest {
  id?: string;
  fund_request_type: 'Aid' | 'Article';
  fund_request_number: string;
  status: 'draft' | 'submitted' | 'approved' | 'rejected' | 'completed';
  total_amount: number;
  aid_type?: string; // Type of aid (e.g., 'Medical Aid', 'Education Aid', 'Accident Aid', etc.)
  gst_number?: string; // GST number for Article type fund requests (applies to all articles)
  supplier_name?: string; // Supplier name for Article type fund requests
  supplier_address?: string; // Supplier address for Article type fund requests
  supplier_city?: string; // Supplier city for Article type fund requests
  supplier_state?: string; // Supplier state for Article type fund requests
  supplier_pincode?: string; // Supplier pincode for Article type fund requests
  purchase_order_number?: string; // Purchase order number in format MASM/MNP00126
  notes?: string;
  article_search_text?: string; // Derived search index for article names (list view search)
  created_at?: string;
  updated_at?: string;
  created_by?: string;
}

export interface FundRequestRecipient {
  id?: string;
  fund_request_id: string;
  beneficiary_type?: 'District' | 'Public' | 'Institutions' | 'Others';
  recipient_name: string;
  beneficiary?: string;
  name_of_beneficiary?: string;
  name_of_institution?: string;
  details?: string;
  fund_requested?: number;
  aadhar_number?: string;
  address?: string;
  cheque_in_favour?: string;
  cheque_no?: string;
  notes?: string;
  district_name?: string;
  created_at?: string;
}

export interface FundRequestArticle {
  id?: string;
  fund_request_id: string;
  article_id: string;
  sl_no?: number;
  beneficiary?: string;
  article_name: string;
  gst_no?: string;
  quantity: number;
  unit_price: number;
  price_including_gst: number;
  value: number;
  cumulative: number;
  cheque_in_favour?: string;
  cheque_no?: string;
  supplier_article_name?: string;
  description?: string;
  created_at?: string;
}

export interface FundRequestWithDetails extends FundRequest {
  recipients?: FundRequestRecipient[];
  articles?: FundRequestArticle[];
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

const isAidItemType = (itemType: unknown): boolean => {
  const value = String(itemType || '').trim().toLowerCase();
  if (!value) return false;
  return value === 'aid' || /\baid\b/.test(value);
};

const inferAidTypeFromRecipients = (
  recipients: Array<{ beneficiary?: string; beneficiary_type?: string }> | undefined
): string | null => {
  if (!recipients || recipients.length === 0) return null;

  for (const recipient of recipients) {
    const text = String(recipient?.beneficiary || '').trim();
    const type = String(recipient?.beneficiary_type || '').trim();
    if (!text) continue;

    // Common formats:
    // "D056 - Education Aid - ₹ 20,000 - Name"
    // "I019 - Environment Aid - ₹ 30,000"
    if (type === 'District' || type === 'Institutions' || type === 'Others') {
      const parts = text.split(' - ').map((p) => p.trim()).filter(Boolean);
      if (parts.length >= 2 && !/^₹/.test(parts[1])) {
        return parts[1];
      }
    }
  }

  return null;
};

const parseBeneficiaryDisplay = (
  value: unknown
): { appNo: string | null; aidLabel: string } => {
  const text = String(value || '').trim();
  if (!text) return { appNo: null, aidLabel: '' };
  const parts = text.split(' - ').map((p) => p.trim()).filter(Boolean);
  return {
    appNo: parts[0] || null,
    aidLabel: parts[1] || '',
  };
};

const textMatches = (a: unknown, b: unknown): boolean => {
  const left = String(a || '').trim().toLowerCase();
  const right = String(b || '').trim().toLowerCase();
  if (!left || !right) return false;
  return left === right || left.includes(right) || right.includes(left);
};

type OrderInsertRow = {
  article_id: string;
  quantity_ordered: number;
  order_date: string;
  status: 'pending' | 'ordered' | 'received' | 'cancelled';
  supplier_name: string | null;
  supplier_contact: string | null;
  unit_price: number;
  total_amount: number;
  notes: string;
  fund_request_id: string;
};

const insertOrderEntriesForFundRequest = async (entries: OrderInsertRow[]): Promise<void> => {
  if (entries.length === 0) return;

  const { error } = await supabase.from('order_entries').insert(entries);
  if (error) {
    console.error('Error creating order entries:', error);
    throw error;
  }
};

/**
 * Find aid article by matching aid_type with articles
 * Uses multiple matching strategies for better accuracy
 */
const findAidArticle = async (aidType: string): Promise<{ id: string; article_name: string } | null> => {
  try {
    const allArticles = await fetchAllArticles(true);
    const aidArticles = allArticles.filter(article => isAidItemType(article.item_type));
    
    if (aidArticles.length === 0) {
      console.warn('No Aid articles found in database');
      return null;
    }

    const aidTypeLower = aidType.toLowerCase().trim();
    
    // Strategy 1: Exact match (case-insensitive) on article_name
    let match = aidArticles.find(article => 
      article.article_name.toLowerCase().trim() === aidTypeLower
    );
    if (match) {
      console.debug(`Found Aid article by exact name match: ${match.article_name}`);
      return { id: match.id, article_name: match.article_name };
    }

    // Strategy 2: Exact match (case-insensitive) on category
    match = aidArticles.find(article => 
      article.category && article.category.toLowerCase().trim() === aidTypeLower
    );
    if (match) {
      console.debug(`Found Aid article by exact category match: ${match.article_name} (category: ${match.category})`);
      return { id: match.id, article_name: match.article_name };
    }

    // Strategy 3: Article name contains aid_type (case-insensitive)
    match = aidArticles.find(article => 
      article.article_name.toLowerCase().includes(aidTypeLower)
    );
    if (match) {
      console.debug(`Found Aid article by partial name match: ${match.article_name}`);
      return { id: match.id, article_name: match.article_name };
    }

    // Strategy 4: Category contains aid_type (case-insensitive)
    match = aidArticles.find(article => 
      article.category && article.category.toLowerCase().includes(aidTypeLower)
    );
    if (match) {
      console.debug(`Found Aid article by partial category match: ${match.article_name} (category: ${match.category})`);
      return { id: match.id, article_name: match.article_name };
    }

    // Strategy 5: Aid_type contains article name (reverse match)
    match = aidArticles.find(article => 
      aidTypeLower.includes(article.article_name.toLowerCase().trim())
    );
    if (match) {
      console.debug(`Found Aid article by reverse name match: ${match.article_name}`);
      return { id: match.id, article_name: match.article_name };
    }

    console.warn(`No Aid article found matching aid_type: "${aidType}". Available Aid articles:`, 
      aidArticles.map(a => `${a.article_name}${a.category ? ` (${a.category})` : ''}`).join(', '));
    return null;
  } catch (error) {
    console.error('Error finding Aid article:', error);
    return null;
  }
};

const resolveAidTargetFromMasterEntry = async (
  recipient: { beneficiary_type?: string; beneficiary?: string },
  preferredAidType?: string | null
): Promise<{ articleId: string; quantity: number } | null> => {
  const { appNo, aidLabel } = parseBeneficiaryDisplay(recipient.beneficiary);
  if (!appNo) return null;

  const aidHint = String(preferredAidType || aidLabel || '').trim();
  const beneficiaryType = String(recipient.beneficiary_type || '').trim();

  const pickAidRow = (
    rows: any[] | null | undefined
  ): { article_id: string; quantity: number } | null => {
    if (!rows || rows.length === 0) return null;

    const normalized = rows
      .map((row) => {
        const article = Array.isArray(row.articles) ? row.articles[0] : row.articles;
        return {
          articleId: row.article_id,
          quantity: Math.max(parseInt(row.quantity, 10) || 1, 1),
          itemType: article?.item_type,
          articleName: article?.article_name,
          category: article?.category,
        };
      })
      .filter((row) => isAidItemType(row.itemType));

    if (normalized.length === 0) return null;

    if (aidHint) {
      const matched = normalized.find((row) =>
        textMatches(row.articleName, aidHint) || textMatches(row.category, aidHint)
      );
      if (matched) {
        return {
          article_id: matched.articleId,
          quantity: 1,
        };
      }
    }

    return {
      article_id: normalized[0].articleId,
      quantity: 1,
    };
  };

  if (beneficiaryType === 'District') {
    const { data } = await supabase
      .from('district_beneficiary_entries')
      .select(`
        article_id,
        quantity,
        articles:article_id (
          item_type,
          article_name,
          category
        )
      `)
      .eq('application_number', appNo)
      .order('created_at', { ascending: false });
    const picked = pickAidRow(data);
    return picked ? { articleId: picked.article_id, quantity: picked.quantity } : null;
  }

  if (beneficiaryType === 'Public') {
    const { data } = await supabase
      .from('public_beneficiary_entries')
      .select(`
        article_id,
        quantity,
        articles:article_id (
          item_type,
          article_name,
          category
        )
      `)
      .eq('application_number', appNo)
      .order('created_at', { ascending: false });
    const picked = pickAidRow(data);
    return picked ? { articleId: picked.article_id, quantity: picked.quantity } : null;
  }

  if (beneficiaryType === 'Institutions' || beneficiaryType === 'Others') {
    const { data } = await supabase
      .from('institutions_beneficiary_entries')
      .select(`
        article_id,
        quantity,
        articles:article_id (
          item_type,
          article_name,
          category
        )
      `)
      .eq('application_number', appNo)
      .order('created_at', { ascending: false });
    const picked = pickAidRow(data);
    return picked ? { articleId: picked.article_id, quantity: picked.quantity } : null;
  }

  return null;
};

const resolveAidOrderTarget = async (
  recipient: { beneficiary_type?: string; beneficiary?: string },
  effectiveAidType?: string | null
): Promise<{ articleId: string; quantity: number } | null> => {
  // Explicit aid_type in FR is authoritative; only fallback to master when absent/unresolvable.
  if (effectiveAidType) {
    const aidArticle = await findAidArticle(effectiveAidType);
    if (aidArticle?.id) {
      return { articleId: aidArticle.id, quantity: 1 };
    }
  }

  const resolvedFromMaster = await resolveAidTargetFromMasterEntry(recipient, effectiveAidType);
  if (resolvedFromMaster) return resolvedFromMaster;

  return null;
};

/**
 * Generate fund request number
 * Format: FR-001, FR-002, etc.
 */
export const generateFundRequestNumber = async (): Promise<string> => {
  try {
    // Get all fund requests to find the highest sequence number
    const { data, error } = await supabase
      .from('fund_request')
      .select('fund_request_number')
      .order('created_at', { ascending: false });

    if (error) throw error;

    let maxSequence = 0;

    if (data && data.length > 0) {
      // Extract sequence numbers from all fund request numbers
      // Handle both old format (FR-2026-0001) and new format (FR-001)
      data.forEach((item) => {
        const number = item.fund_request_number;
        
        // Try new format first: FR-001, FR-002, etc.
        const newFormatMatch = number.match(/^FR-(\d+)$/);
        if (newFormatMatch) {
          const seq = parseInt(newFormatMatch[1], 10);
          if (seq > maxSequence) {
            maxSequence = seq;
          }
        } else {
          // Try old format: FR-2026-0001, etc.
          const oldFormatMatch = number.match(/^FR-\d{4}-(\d+)$/);
          if (oldFormatMatch) {
            const seq = parseInt(oldFormatMatch[1], 10);
            if (seq > maxSequence) {
              maxSequence = seq;
            }
          }
        }
      });
    }

    // Generate next sequence number
    const nextSequence = maxSequence + 1;
    return `FR-${nextSequence.toString().padStart(3, '0')}`;
  } catch (error) {
    console.error('Error generating fund request number:', error);
    // Fallback: use timestamp-based number
    const timestamp = Date.now().toString().slice(-6);
    return `FR-${timestamp}`;
  }
};

/**
 * Generate purchase order number
 * Format: MASM/MNP00126, MASM/MNP00226, etc.
 * The format is: MASM/MNP + 3-digit sequence + 2-digit year
 * Example: 00126 = 001 (sequence) + 26 (year 2026)
 * Next: 00226 = 002 (sequence) + 26 (year 2026)
 */
export const generatePurchaseOrderNumber = async (): Promise<string> => {
  try {
    // Hardcoded year suffix (26 for year 2026)
    const yearSuffix = 26;

    // Get all fund requests with purchase order numbers to find the highest sequence number
    const { data, error } = await supabase
      .from('fund_request')
      .select('purchase_order_number')
      .not('purchase_order_number', 'is', null)
      .order('created_at', { ascending: false });

    if (error) throw error;

    let maxSequence = 0; // Start from 1, so default max is 0

    if (data && data.length > 0) {
      // Extract sequence numbers from all purchase order numbers
      // Format: MASM/MNP00126 (5 digits: 3-digit sequence + 2-digit year)
      data.forEach((item) => {
        const poNumber = item.purchase_order_number;
        if (!poNumber || typeof poNumber !== 'string') return;
        
        // Match format: MASM/MNP followed by 5 digits
        const match = poNumber.match(/MASM\/MNP(\d{5})$/);
        if (match) {
          const fullNumber = match[1];
          const numberYear = parseInt(fullNumber.slice(-2), 10);
          
          // Only consider numbers with the same year suffix (26)
          if (numberYear === yearSuffix) {
            const sequence = parseInt(fullNumber.slice(0, 3), 10);
            console.log(`Found PO number: ${poNumber}, extracted sequence: ${sequence}, year: ${numberYear}`);
            if (sequence > maxSequence) {
              maxSequence = sequence;
            }
          } else {
            console.log(`Skipping PO number: ${poNumber} (year ${numberYear} doesn't match ${yearSuffix})`);
          }
        } else {
          console.log(`PO number doesn't match format: ${poNumber}`);
        }
      });
    }

    // Generate next sequence number (increment sequence, keep year)
    const nextSequence = maxSequence + 1;
    const sequenceStr = nextSequence.toString().padStart(3, '0');
    const generatedNumber = `MASM/MNP${sequenceStr}${yearSuffix}`;
    console.log(`Max sequence found: ${maxSequence}, next sequence: ${nextSequence}, generated: ${generatedNumber}`);
    return generatedNumber;
  } catch (error) {
    console.error('Error generating purchase order number:', error);
    // Fallback: use sequence 001 with year 26
    const yearSuffix = 26;
    console.log('Fallback: using sequence 001 with year', yearSuffix);
    return `MASM/MNP001${yearSuffix}`;
  }
};

/**
 * Fetch total amount of all previous fund requests (before the given fund request)
 */
export const fetchPreviousFundRequestTotal = async (currentFundRequestId: string, currentCreatedAt: string): Promise<number> => {
  try {
    const { data, error } = await supabase
      .from('fund_request')
      .select('total_amount')
      .lt('created_at', currentCreatedAt)
      .neq('id', currentFundRequestId);

    if (error) {
      console.error('Error fetching previous fund request totals:', error);
      throw error;
    }

    const total = (data || []).reduce((sum, fr) => sum + (parseFloat(fr.total_amount) || 0), 0);
    return total;
  } catch (error) {
    console.error('Failed to fetch previous fund request totals:', error);
    throw error;
  }
};

/**
 * Fetch all unique aid types from existing fund requests
 */
export const fetchExistingAidTypes = async (): Promise<string[]> => {
  try {
    const { data, error } = await supabase
      .from('fund_request')
      .select('aid_type')
      .eq('fund_request_type', 'Aid')
      .not('aid_type', 'is', null);

    if (error) {
      console.error('Error fetching aid types:', error);
      throw error;
    }

    // Extract unique aid types and sort them
    const uniqueAidTypes = Array.from(
      new Set(
        (data || [])
          .map(item => item.aid_type)
          .filter((type): type is string => !!type)
      )
    ).sort();

    return uniqueAidTypes;
  } catch (error) {
    console.error('Failed to fetch aid types:', error);
    throw error;
  }
};

/**
 * Fetch all fund requests with optional filters
 */
export const fetchFundRequests = async (filters?: {
  fund_request_type?: 'Aid' | 'Article';
  status?: string;
  start_date?: string;
  end_date?: string;
}): Promise<FundRequest[]> => {
  try {
    let query = supabase
      .from('fund_request')
      .select('*, fund_request_articles(article_name, supplier_article_name), fund_request_recipients(beneficiary, beneficiary_type)')
      .order('created_at', { ascending: false });

    if (filters?.fund_request_type) {
      query = query.eq('fund_request_type', filters.fund_request_type);
    }

    if (filters?.status) {
      query = query.eq('status', filters.status);
    }

    if (filters?.start_date) {
      query = query.gte('created_at', filters.start_date);
    }

    if (filters?.end_date) {
      // Include the full end date by querying records before the next day (exclusive).
      const endDate = new Date(`${filters.end_date}T00:00:00`);
      endDate.setDate(endDate.getDate() + 1);
      const nextDay = `${endDate.getFullYear()}-${String(endDate.getMonth() + 1).padStart(2, '0')}-${String(endDate.getDate()).padStart(2, '0')}`;
      query = query.lt('created_at', nextDay);
    }

    const { data, error } = await query;

    if (error) {
      console.error('Error fetching fund requests:', error);
      throw error;
    }

    return (data || []).map(item => {
      const articleSearchText = (item.fund_request_articles || [])
        .flatMap((article: { article_name?: string; supplier_article_name?: string }) => [
          article.article_name || '',
          article.supplier_article_name || '',
        ])
        .join(' ')
        .trim();

      const inferredAidType = item.aid_type || inferAidTypeFromRecipients(item.fund_request_recipients);

      return {
        ...item,
        total_amount: parseFloat(item.total_amount) || 0,
        aid_type: inferredAidType || item.aid_type || null,
        article_search_text: articleSearchText,
      };
    });
  } catch (error) {
    console.error('Failed to fetch fund requests:', error);
    throw error;
  }
};

/**
 * Fetch single fund request with recipients/articles
 */
export const fetchFundRequestById = async (id: string): Promise<FundRequestWithDetails | null> => {
  try {
    const { data: fundRequest, error: fundRequestError } = await supabase
      .from('fund_request')
      .select('*')
      .eq('id', id)
      .single();

    if (fundRequestError) {
      console.error('Error fetching fund request:', fundRequestError);
      throw fundRequestError;
    }

    if (!fundRequest) return null;

    const result: FundRequestWithDetails = {
      ...fundRequest,
      total_amount: parseFloat(fundRequest.total_amount) || 0,
    };

    // Fetch recipients if Aid type
    if (fundRequest.fund_request_type === 'Aid') {
      const { data: recipients, error: recipientsError } = await supabase
        .from('fund_request_recipients')
        .select('*')
        .eq('fund_request_id', id)
        .order('created_at', { ascending: true });

      if (!recipientsError && recipients) {
        result.recipients = recipients.map(r => ({
          ...r,
          fund_requested: parseFloat(r.fund_requested) || 0,
        }));
      }
    }

    // Fetch articles if Article type
    if (fundRequest.fund_request_type === 'Article') {
      const { data: articles, error: articlesError } = await supabase
        .from('fund_request_articles')
        .select('*')
        .eq('fund_request_id', id)
        .order('sl_no', { ascending: true })
        .order('created_at', { ascending: true });

      if (!articlesError && articles) {
        result.articles = articles.map(item => ({
          ...item,
          quantity: parseInt(item.quantity) || 0,
          unit_price: parseFloat(item.unit_price) || 0,
          price_including_gst: parseFloat(item.price_including_gst) || 0,
          value: parseFloat(item.value) || 0,
          cumulative: parseFloat(item.cumulative) || 0,
        }));
      }
    }

    return result;
  } catch (error) {
    console.error('Failed to fetch fund request:', error);
    throw error;
  }
};

/**
 * Create fund request with recipients/articles
 */
export const createFundRequest = async (data: {
  fundRequest: Omit<FundRequest, 'id' | 'created_at' | 'updated_at'>;
  recipients?: Omit<FundRequestRecipient, 'id' | 'fund_request_id' | 'created_at'>[];
  articles?: Omit<FundRequestArticle, 'id' | 'fund_request_id' | 'created_at'>[];
}): Promise<FundRequestWithDetails> => {
  try {
    const userId = await getCurrentUserId();
    
    // Generate fund request number if not provided
    if (!data.fundRequest.fund_request_number) {
      data.fundRequest.fund_request_number = await generateFundRequestNumber();
    }

    // Insert fund request
    const { data: fundRequest, error: fundRequestError } = await supabase
      .from('fund_request')
      .insert([{
        ...data.fundRequest,
        created_by: userId,
      }])
      .select()
      .single();

    if (fundRequestError) {
      console.error('Error creating fund request:', fundRequestError);
      throw fundRequestError;
    }

    const result: FundRequestWithDetails = {
      ...fundRequest,
      total_amount: parseFloat(fundRequest.total_amount) || 0,
    };

    // Insert recipients if Aid type
    if (data.fundRequest.fund_request_type === 'Aid' && data.recipients && data.recipients.length > 0) {
      const { data: recipients, error: recipientsError } = await supabase
        .from('fund_request_recipients')
        .insert(
          data.recipients.map(recipient => ({
            ...recipient,
            fund_request_id: fundRequest.id,
          }))
        )
        .select();

      if (recipientsError) {
        console.error('Error creating recipients:', recipientsError);
        throw recipientsError;
      }

      result.recipients = recipients?.map(r => ({
        ...r,
        fund_requested: parseFloat(r.fund_requested) || 0,
      })) || [];

      // Create order entries for Aid fund requests
      if (recipients && recipients.length > 0) {
        try {
          const effectiveAidType =
            String(data.fundRequest.aid_type || '').trim() ||
            inferAidTypeFromRecipients(recipients);

          const orderRows: OrderInsertRow[] = [];
          for (const recipient of recipients) {
            const target = await resolveAidOrderTarget(recipient, effectiveAidType);
            if (!target) {
              console.warn(
                `Could not resolve Aid article for recipient "${recipient.recipient_name || recipient.name_of_beneficiary || 'Recipient'}" in ${fundRequest.fund_request_number}.`
              );
              continue;
            }

            orderRows.push({
              article_id: target.articleId,
              quantity_ordered: target.quantity,
              order_date: new Date().toISOString().split('T')[0],
              status: 'pending',
              supplier_name: null,
              supplier_contact: null,
              unit_price: parseFloat(recipient.fund_requested) || 0,
              total_amount: parseFloat(recipient.fund_requested) || 0,
              notes: `Created from Aid Fund Request: ${fundRequest.fund_request_number} - ${recipient.recipient_name || recipient.name_of_beneficiary || 'Recipient'}`,
              fund_request_id: fundRequest.id,
            });
          }

          if (orderRows.length > 0) {
            await insertOrderEntriesForFundRequest(orderRows);
            console.log(`Created ${orderRows.length} order entries for Aid fund request: ${fundRequest.fund_request_number}`);
          } else {
            console.warn(`No Aid order entries created for ${fundRequest.fund_request_number}.`);
          }
        } catch (orderError) {
          console.error('Error creating order entries for Aid fund request:', orderError);
          // Don't throw - order creation failure shouldn't fail fund request creation
        }
      }
    }

    // Insert articles if Article type
    if (data.fundRequest.fund_request_type === 'Article' && data.articles && data.articles.length > 0) {
      // Use cumulative from article data (set to 0 in form, but keep for backward compatibility)
      const articlesWithCumulative = data.articles.map(article => ({
        ...article,
        cumulative: article.cumulative || 0, // Use provided cumulative or default to 0
      }));

      const { data: articles, error: articlesError } = await supabase
        .from('fund_request_articles')
        .insert(
          articlesWithCumulative.map(article => ({
            ...article,
            fund_request_id: fundRequest.id,
          }))
        )
        .select();

      if (articlesError) {
        console.error('Error creating articles:', articlesError);
        throw articlesError;
      }

      result.articles = articles?.map(item => ({
        ...item,
        quantity: parseInt(item.quantity) || 0,
        unit_price: parseFloat(item.unit_price) || 0,
        price_including_gst: parseFloat(item.price_including_gst) || 0,
        value: parseFloat(item.value) || 0,
        cumulative: parseFloat(item.cumulative) || 0,
      })) || [];

      // Create order entries for each article
      if (articles && articles.length > 0) {
        try {
          const orderRows: OrderInsertRow[] = articles.map(article => ({
              article_id: article.article_id,
              quantity_ordered: article.quantity,
              order_date: new Date().toISOString().split('T')[0],
              status: 'pending',
              supplier_name: null,
              supplier_contact: null,
              unit_price: article.unit_price,
              total_amount: article.value,
              notes: `Created from Fund Request: ${fundRequest.fund_request_number}`,
              fund_request_id: fundRequest.id,
            }));

          await insertOrderEntriesForFundRequest(orderRows);
        } catch (orderError) {
          console.error('Error creating order entries:', orderError);
          // Don't throw - order creation failure shouldn't fail fund request creation
        }
      }
    }

    // Log audit action
    await logAction(userId, 'CREATE', 'fund_request', fundRequest.id, {
      entity_name: fundRequest.fund_request_number,
      entity_summary: `Fund Request: ${fundRequest.fund_request_number} (${fundRequest.fund_request_type})`,
      new_values: {
        fund_request_type: fundRequest.fund_request_type,
        fund_request_number: fundRequest.fund_request_number,
        total_amount: fundRequest.total_amount,
      },
    });

    return result;
  } catch (error) {
    console.error('Failed to create fund request:', error);
    throw error;
  }
};

/**
 * Update fund request with recipients/articles
 */
export const updateFundRequest = async (
  id: string,
  data: {
    fundRequest: Partial<Omit<FundRequest, 'id' | 'created_at' | 'updated_at'>>;
    recipients?: Omit<FundRequestRecipient, 'id' | 'fund_request_id' | 'created_at'>[];
    articles?: Omit<FundRequestArticle, 'id' | 'fund_request_id' | 'created_at'>[];
  }
): Promise<FundRequestWithDetails> => {
  try {
    const userId = await getCurrentUserId();

    // Get existing fund request for audit log
    const existing = await fetchFundRequestById(id);
    if (!existing) {
      throw new Error('Fund request not found');
    }

    // Update fund request
    const { data: fundRequest, error: fundRequestError } = await supabase
      .from('fund_request')
      .update(data.fundRequest)
      .eq('id', id)
      .select()
      .single();

    if (fundRequestError) {
      console.error('Error updating fund request:', fundRequestError);
      throw fundRequestError;
    }

    const result: FundRequestWithDetails = {
      ...fundRequest,
      total_amount: parseFloat(fundRequest.total_amount) || 0,
    };

    // Update recipients if Aid type
    if (data.fundRequest.fund_request_type === 'Aid' && data.recipients !== undefined) {
      // Delete existing order entries for this fund request (before updating recipients)
      const { error: deleteOrdersError } = await supabase
        .from('order_entries')
        .delete()
        .eq('fund_request_id', id);

      if (deleteOrdersError) {
        console.error('Error deleting old order entries:', deleteOrdersError);
        // Continue with update even if order deletion fails
      }

      // Delete existing recipients
      await supabase
        .from('fund_request_recipients')
        .delete()
        .eq('fund_request_id', id);

      // Insert new recipients
      if (data.recipients.length > 0) {
        const { data: recipients, error: recipientsError } = await supabase
          .from('fund_request_recipients')
          .insert(
            data.recipients.map(recipient => ({
              ...recipient,
              fund_request_id: id,
            }))
          )
          .select();

        if (recipientsError) {
          console.error('Error updating recipients:', recipientsError);
          throw recipientsError;
        }

        result.recipients = recipients?.map(r => ({
          ...r,
          fund_requested: parseFloat(r.fund_requested) || 0,
        })) || [];

        // Create new order entries for Aid fund requests
        const updatedFundRequest = await fetchFundRequestById(id);
        if (recipients && recipients.length > 0) {
          try {
            const effectiveAidType =
              String(updatedFundRequest?.aid_type || '').trim() ||
              inferAidTypeFromRecipients(recipients);

            const orderRows: OrderInsertRow[] = [];
            for (const recipient of recipients) {
              const target = await resolveAidOrderTarget(recipient, effectiveAidType);
              if (!target) {
                console.warn(
                  `Could not resolve Aid article for recipient "${recipient.recipient_name || recipient.name_of_beneficiary || 'Recipient'}" in ${fundRequest.fund_request_number}.`
                );
                continue;
              }

              orderRows.push({
                article_id: target.articleId,
                quantity_ordered: target.quantity,
                order_date: new Date().toISOString().split('T')[0],
                status: 'pending',
                supplier_name: null,
                supplier_contact: null,
                unit_price: parseFloat(recipient.fund_requested) || 0,
                total_amount: parseFloat(recipient.fund_requested) || 0,
                notes: `Created from Aid Fund Request: ${fundRequest.fund_request_number} - ${recipient.recipient_name || recipient.name_of_beneficiary || 'Recipient'}`,
                fund_request_id: id,
              });
            }

            if (orderRows.length > 0) {
              await insertOrderEntriesForFundRequest(orderRows);
              console.log(`Created ${orderRows.length} order entries for Aid fund request update: ${fundRequest.fund_request_number}`);
            } else {
              console.warn(`No Aid order entries created for update ${fundRequest.fund_request_number}.`);
            }
          } catch (orderError) {
            console.error('Error creating order entries for Aid fund request update:', orderError);
            // Don't throw - order creation failure shouldn't fail fund request update
          }
        }
      } else {
        result.recipients = [];
      }
    }

    // Update articles if Article type
    if (data.fundRequest.fund_request_type === 'Article' && data.articles !== undefined) {
      // Delete existing order entries for this fund request (before updating articles)
      const { error: deleteOrdersError } = await supabase
        .from('order_entries')
        .delete()
        .eq('fund_request_id', id);

      if (deleteOrdersError) {
        console.error('Error deleting old order entries:', deleteOrdersError);
        // Continue with update even if order deletion fails
      }

      // Delete existing articles
      await supabase
        .from('fund_request_articles')
        .delete()
        .eq('fund_request_id', id);

      // Insert new articles
      if (data.articles.length > 0) {
        // Use cumulative from article data (set to 0 in form, but keep for backward compatibility)
        const articlesWithCumulative = data.articles.map(article => ({
          ...article,
          cumulative: article.cumulative || 0, // Use provided cumulative or default to 0
        }));

        const { data: articles, error: articlesError } = await supabase
          .from('fund_request_articles')
          .insert(
            articlesWithCumulative.map(article => ({
              ...article,
              fund_request_id: id,
            }))
          )
          .select();

        if (articlesError) {
          console.error('Error updating articles:', articlesError);
          throw articlesError;
        }

        result.articles = articles?.map(item => ({
          ...item,
          quantity: parseInt(item.quantity) || 0,
          unit_price: parseFloat(item.unit_price) || 0,
          price_including_gst: parseFloat(item.price_including_gst) || 0,
          value: parseFloat(item.value) || 0,
          cumulative: parseFloat(item.cumulative) || 0,
        })) || [];

        // Create order entries for each article
        if (articles && articles.length > 0) {
          try {
            const orderRows: OrderInsertRow[] = articles.map(article => ({
                article_id: article.article_id,
                quantity_ordered: article.quantity,
                order_date: new Date().toISOString().split('T')[0],
                status: 'pending',
                supplier_name: null,
                supplier_contact: null,
                unit_price: article.unit_price,
                total_amount: article.value,
                notes: `Created from Fund Request: ${fundRequest.fund_request_number}`,
                fund_request_id: id,
              }));

            await insertOrderEntriesForFundRequest(orderRows);
          } catch (orderError) {
            console.error('Error creating order entries:', orderError);
            // Don't throw - order creation failure shouldn't fail fund request update
          }
        }
      } else {
        result.articles = [];
      }
    }

    // Log audit action
    await logAction(userId, 'UPDATE', 'fund_request', id, {
      entity_name: fundRequest.fund_request_number,
      entity_summary: `Fund Request: ${fundRequest.fund_request_number} (${fundRequest.fund_request_type})`,
      old_values: {
        status: existing.status,
        total_amount: existing.total_amount,
      },
      new_values: {
        status: fundRequest.status,
        total_amount: fundRequest.total_amount,
      },
    });

    return result;
  } catch (error) {
    console.error('Failed to update fund request:', error);
    throw error;
  }
};

/**
 * Delete fund request (hard delete)
 */
export const deleteFundRequest = async (id: string): Promise<void> => {
  try {
    const userId = await getCurrentUserId();

    // Get existing fund request for audit log
    const existing = await fetchFundRequestById(id);
    if (!existing) {
      throw new Error('Fund request not found');
    }

    // Delete all order entries associated with this fund request
    // This ensures order counts are properly updated when FR is deleted
    const { data: orderEntries, error: orderEntriesError } = await supabase
      .from('order_entries')
      .select('id')
      .eq('fund_request_id', id);

    if (orderEntriesError) {
      console.error('Error fetching order entries for deletion:', orderEntriesError);
      // Continue with deletion even if fetching order entries fails
    } else if (orderEntries && orderEntries.length > 0) {
      // Delete all order entries
      const { error: deleteOrdersError } = await supabase
        .from('order_entries')
        .delete()
        .eq('fund_request_id', id);

      if (deleteOrdersError) {
        console.error('Error deleting order entries:', deleteOrdersError);
        // Continue with fund request deletion even if order deletion fails
      }
    }

    // Delete fund request (cascade will delete recipients/articles)
    const { error, data } = await supabase
      .from('fund_request')
      .delete()
      .eq('id', id)
      .select();

    if (error) {
      console.error('Error deleting fund request:', error);
      // Provide more specific error message
      if (error.code === '42501') {
        throw new Error('Permission denied: You do not have permission to delete fund requests.');
      }
      throw new Error(`Failed to delete fund request: ${error.message || 'Unknown error'}`);
    }

    // Verify deletion succeeded
    if (!data || data.length === 0) {
      throw new Error('Fund request deletion failed: No rows were deleted. This may be due to insufficient permissions.');
    }

    // Log audit action
    await logAction(userId, 'DELETE', 'fund_request', id, {
      entity_name: existing.fund_request_number,
      entity_summary: `Fund Request: ${existing.fund_request_number} (${existing.fund_request_type})`,
      old_values: {
        fund_request_type: existing.fund_request_type,
        fund_request_number: existing.fund_request_number,
        status: existing.status,
      },
    });
  } catch (error) {
    console.error('Failed to delete fund request:', error);
    throw error;
  }
};
