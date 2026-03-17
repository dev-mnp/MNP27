import { supabase } from '../lib/supabase';
import { logAction } from './auditLogService';

export interface OrderEntry {
  id?: string;
  article_id: string;
  quantity_ordered: number;
  order_date: string; // Date in YYYY-MM-DD format
  status: 'pending' | 'ordered' | 'received' | 'cancelled';
  supplier_name?: string | null;
  supplier_contact?: string | null;
  unit_price?: number | null;
  total_amount: number;
  expected_delivery_date?: string | null; // Date in YYYY-MM-DD format
  notes?: string | null;
  fund_request_id?: string | null;
  created_at?: string;
  updated_at?: string;
  created_by?: string | null;
}

export interface OrderEntryWithArticle extends OrderEntry {
  articles?: {
    article_name: string;
    cost_per_unit: number;
  };
}

export interface ArticleOrderSummary {
  articleId: string;
  articleName: string;
  totalQuantityNeeded: number;
  totalQuantityOrdered: number;
  totalQuantityReceived: number;
  totalQuantityPending: number;
  totalValueNeeded: number;
  totalValueOrdered: number;
  orders: OrderEntryWithArticle[];
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
 * Create a new order entry
 */
export const createOrderEntry = async (
  order: Omit<OrderEntry, 'id' | 'created_at' | 'updated_at'>
): Promise<OrderEntry> => {
  try {
    const { data, error } = await supabase
      .from('order_entries')
      .insert(order)
      .select()
      .single();

    if (error) {
      console.error('Error creating order entry:', error);
      throw error;
    }

    // Log audit action with new values
    const userId = await getCurrentUserId();
    await logAction(userId, 'CREATE', 'order', data.id, {
      entity_summary: `Order Entry for Article: ${data.article_id}`,
      new_values: {
        article_id: data.article_id,
        quantity_ordered: data.quantity_ordered,
        order_date: data.order_date,
        status: data.status,
        total_amount: data.total_amount,
        supplier_name: data.supplier_name,
        supplier_contact: data.supplier_contact,
        unit_price: data.unit_price,
        expected_delivery_date: data.expected_delivery_date,
      },
    });

    return data;
  } catch (error) {
    console.error('Failed to create order entry:', error);
    throw error;
  }
};

/**
 * Update an existing order entry
 */
export const updateOrderEntry = async (
  id: string,
  updates: Partial<OrderEntry>
): Promise<OrderEntry> => {
  try {
    // Fetch old values before update
    const { data: oldData } = await supabase
      .from('order_entries')
      .select('*')
      .eq('id', id)
      .single();

    const { data, error } = await supabase
      .from('order_entries')
      .update(updates)
      .eq('id', id)
      .select()
      .single();

    if (error) {
      console.error('Error updating order entry:', error);
      throw error;
    }

    // Log audit action with old and new values
    const userId = await getCurrentUserId();
    const actionType = updates.status ? 'STATUS_CHANGE' : 'UPDATE';
    const updatedFields = Object.keys(updates);
    const oldValues: Record<string, any> = {};
    const newValues: Record<string, any> = {};

    updatedFields.forEach((field) => {
      if (oldData) {
        oldValues[field] = oldData[field as keyof typeof oldData];
      }
      newValues[field] = updates[field as keyof typeof updates];
    });

    await logAction(userId, actionType, 'order', id, {
      entity_summary: `Order Entry for Article: ${data.article_id}`,
      old_values: oldValues,
      new_values: newValues,
      updated_fields: updatedFields,
      affected_fields: updatedFields,
      ...(actionType === 'STATUS_CHANGE' ? {
        previous_status: oldData?.status,
        new_status: data.status,
      } : {}),
    });

    return data;
  } catch (error) {
    console.error('Failed to update order entry:', error);
    throw error;
  }
};

/**
 * Delete an order entry
 */
export const deleteOrderEntry = async (id: string): Promise<void> => {
  try {
    // Get entry details before deletion for audit log
    const { data: entryData } = await supabase
      .from('order_entries')
      .select('article_id, quantity_ordered, status, order_date, total_amount, supplier_name, supplier_contact')
      .eq('id', id)
      .single();

    const { error } = await supabase
      .from('order_entries')
      .delete()
      .eq('id', id);

    if (error) {
      console.error('Error deleting order entry:', error);
      throw error;
    }

    // Log audit action with deleted values
    const userId = await getCurrentUserId();
    await logAction(userId, 'DELETE', 'order', id, {
      entity_summary: `Order Entry for Article: ${entryData?.article_id}`,
      deleted_values: entryData ? {
        article_id: entryData.article_id,
        quantity_ordered: entryData.quantity_ordered,
        order_date: entryData.order_date,
        status: entryData.status,
        total_amount: entryData.total_amount,
        supplier_name: entryData.supplier_name,
        supplier_contact: entryData.supplier_contact,
      } : {},
    });
  } catch (error) {
    console.error('Failed to delete order entry:', error);
    throw error;
  }
};

/**
 * Fetch all order entries for a specific article
 */
export const fetchOrderEntriesByArticle = async (
  articleId: string
): Promise<OrderEntryWithArticle[]> => {
  try {
    const { data, error } = await supabase
      .from('order_entries')
      .select(`
        *,
        articles:article_id (
          article_name,
          cost_per_unit
        )
      `)
      .eq('article_id', articleId)
      .order('order_date', { ascending: false })
      .order('created_at', { ascending: false });

    if (error) {
      console.error('Error fetching order entries:', error);
      throw error;
    }

    return data || [];
  } catch (error) {
    console.error('Failed to fetch order entries:', error);
    throw error;
  }
};

/**
 * Check if a string is a valid UUID format
 */
const isValidUUID = (uuid: string): boolean => {
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  return uuidRegex.test(uuid);
};

/**
 * Get order summary for all articles
 * This aggregates order entries by article and calculates totals
 */
export const getOrderSummaryByArticle = async (
  articleIds: string[]
): Promise<Map<string, ArticleOrderSummary>> => {
  try {
    if (articleIds.length === 0) {
      return new Map();
    }

    // Filter to only valid UUIDs for database query (mock data may have non-UUID IDs)
    const validUUIDs = articleIds.filter(id => isValidUUID(id));
    
    // Initialize summary for all articles (including non-UUIDs from mock data)
    const summaryMap = new Map<string, ArticleOrderSummary>();
    articleIds.forEach((articleId) => {
      summaryMap.set(articleId, {
        articleId,
        articleName: '',
        totalQuantityNeeded: 0,
        totalQuantityOrdered: 0,
        totalQuantityReceived: 0,
        totalQuantityPending: 0,
        totalValueNeeded: 0,
        totalValueOrdered: 0,
        orders: [],
      });
    });

    // Only query database if we have valid UUIDs
    if (validUUIDs.length === 0) {
      return summaryMap;
    }

    const { data, error } = await supabase
      .from('order_entries')
      .select(`
        *,
        articles:article_id (
          article_name,
          cost_per_unit
        )
      `)
      .in('article_id', validUUIDs)
      .order('order_date', { ascending: false });

    if (error) {
      console.error('Error fetching order summary:', error);
      throw error;
    }

    const entries = (data || []) as OrderEntryWithArticle[];

    // Aggregate order entries by article
    entries.forEach((entry) => {
      const summary = summaryMap.get(entry.article_id);
      if (!summary) return;

      if (!summary.articleName && entry.articles?.article_name) {
        summary.articleName = entry.articles.article_name;
      }

      summary.orders.push(entry);

      // Calculate totals based on status (exclude cancelled orders)
      if (entry.status === 'cancelled') {
        // Skip cancelled orders in totals
      } else if (entry.status === 'received') {
        summary.totalQuantityReceived += entry.quantity_ordered;
        summary.totalQuantityOrdered += entry.quantity_ordered;
      } else if (entry.status === 'ordered' || entry.status === 'pending') {
        summary.totalQuantityOrdered += entry.quantity_ordered;
      }

      // Only count value for non-cancelled orders
      if (entry.status !== 'cancelled') {
        const amount = typeof entry.total_amount === 'string'
          ? parseFloat(entry.total_amount)
          : (entry.total_amount || 0);
        summary.totalValueOrdered += amount;
      }
    });

    return summaryMap;
  } catch (error) {
    console.error('Failed to get order summary:', error);
    throw error;
  }
};