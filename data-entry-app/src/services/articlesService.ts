import { supabase, withTimeoutAndRetry } from '../lib/supabase';
import type { Article } from '../data/mockData';
import { logAction } from './auditLogService';

export interface ArticleRecord {
  id: string;
  article_name: string;
  article_name_tk?: string;
  cost_per_unit: number;
  item_type: string;
  category?: string;
  master_category?: string;
  combo?: boolean;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

/**
 * Fetch all articles from the database (including inactive)
 */
export const fetchAllArticles = async (includeInactive: boolean = true): Promise<ArticleRecord[]> => {
  const startTime = Date.now();
  console.debug('fetchAllArticles: Starting fetch, includeInactive:', includeInactive);
  
  try {
    const result = await withTimeoutAndRetry(async () => {
      let query = supabase
        .from('articles')
        .select('*')
        .order('article_name', { ascending: true });

      if (!includeInactive) {
        query = query.eq('is_active', true);
      }

      const { data, error } = await query;

      if (error) {
        console.error('fetchAllArticles: Supabase query error:', error);
        throw error;
      }

      return data;
    }, 1, 15000); // 1 retry, 15 second timeout

    const duration = Date.now() - startTime;
    console.debug(`fetchAllArticles: Fetch completed in ${duration}ms, count: ${result?.length || 0}`);

    return (result || []).map((record) => ({
      id: record.id,
      article_name: record.article_name,
      article_name_tk: record.article_name_tk || null,
      cost_per_unit: parseFloat(record.cost_per_unit) || 0,
      item_type: record.item_type || 'Article',
      category: record.category || null,
      master_category: record.master_category || null,
      combo: record.combo ?? false,
      is_active: record.is_active ?? true,
      created_at: record.created_at,
      updated_at: record.updated_at,
    }));
  } catch (error) {
    const duration = Date.now() - startTime;
    console.error(`fetchAllArticles: Failed after ${duration}ms:`, error);
    throw error;
  }
};

/**
 * Fetch all active articles from the database
 */
export const fetchArticles = async (): Promise<Article[]> => {
  const startTime = Date.now();
  console.debug('fetchArticles: Starting fetch');
  
  try {
    const result = await withTimeoutAndRetry(async () => {
      const { data, error } = await supabase
        .from('articles')
        .select('*')
        .eq('is_active', true)
        .order('article_name', { ascending: true });

      if (error) {
        console.error('fetchArticles: Supabase query error:', error);
        throw error;
      }

      return data;
    }, 1, 15000); // 1 retry, 15 second timeout

    const duration = Date.now() - startTime;
    console.debug(`fetchArticles: Fetch completed in ${duration}ms, count: ${result?.length || 0}`);

    // Transform database records to Article interface
    return (result || []).map((record) => ({
      id: record.id,
      name: record.article_name,
      costPerUnit: parseFloat(record.cost_per_unit) || 0,
      itemType: record.item_type || 'Article',
      category: record.category || undefined,
    }));
  } catch (error) {
    const duration = Date.now() - startTime;
    console.error(`fetchArticles: Failed after ${duration}ms:`, error);
    throw error;
  }
};

/**
 * Fetch a single article by ID
 */
export const fetchArticleById = async (id: string): Promise<Article | null> => {
  const startTime = Date.now();
  console.debug('fetchArticleById: Starting fetch for id:', id);
  
  try {
    const result = await withTimeoutAndRetry(async () => {
      const { data, error } = await supabase
        .from('articles')
        .select('*')
        .eq('id', id)
        .eq('is_active', true)
        .single();

      if (error) {
        console.error('fetchArticleById: Supabase query error:', error);
        throw error;
      }

      return data;
    }, 1, 15000); // 1 retry, 15 second timeout

    const duration = Date.now() - startTime;
    console.debug(`fetchArticleById: Fetch completed in ${duration}ms`);

    if (!result) return null;

    return {
      id: result.id,
      name: result.article_name,
      costPerUnit: parseFloat(result.cost_per_unit) || 0,
      itemType: result.item_type || 'Article',
      category: result.category || undefined,
    };
  } catch (error) {
    const duration = Date.now() - startTime;
    console.error(`fetchArticleById: Failed after ${duration}ms:`, error);
    return null;
  }
};

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
 * Create a new article
 */
export const createArticle = async (article: {
  article_name: string;
  article_name_tk?: string;
  cost_per_unit: number;
  item_type: string;
  category?: string;
  master_category?: string;
  combo?: boolean;
}): Promise<ArticleRecord> => {
  try {
    const { data, error } = await supabase
      .from('articles')
      .insert([article])
      .select()
      .single();

    if (error) {
      console.error('Error creating article:', error);
      throw error;
    }

    const result = {
      id: data.id,
      article_name: data.article_name,
      article_name_tk: data.article_name_tk || null,
      cost_per_unit: parseFloat(data.cost_per_unit) || 0,
      item_type: data.item_type || 'Article',
      category: data.category || null,
      master_category: data.master_category || null,
      combo: data.combo ?? false,
      is_active: data.is_active ?? true,
      created_at: data.created_at,
      updated_at: data.updated_at,
    };

    // Log audit action with new values
    const userId = await getCurrentUserId();
    await logAction(userId, 'CREATE', 'article', result.id, {
      entity_name: result.article_name,
      entity_summary: `Article: ${result.article_name}`,
      new_values: {
        article_name: result.article_name,
        article_name_tk: result.article_name_tk,
        cost_per_unit: result.cost_per_unit,
        item_type: result.item_type,
        category: result.category,
        master_category: result.master_category,
        combo: result.combo,
        is_active: result.is_active,
      },
    });

    return result;
  } catch (error) {
    console.error('Failed to create article:', error);
    throw error;
  }
};

/**
 * Update an existing article
 */
export const updateArticle = async (
  id: string,
  updates: {
    article_name?: string;
    article_name_tk?: string;
    cost_per_unit?: number;
    item_type?: string;
    category?: string;
    master_category?: string;
    combo?: boolean;
  }
): Promise<ArticleRecord> => {
  try {
    // Fetch old values before update
    const { data: oldData } = await supabase
      .from('articles')
      .select('*')
      .eq('id', id)
      .single();

    const { data, error } = await supabase
      .from('articles')
      .update(updates)
      .eq('id', id)
      .select()
      .single();

    if (error) {
      console.error('Error updating article:', error);
      throw error;
    }

    const result = {
      id: data.id,
      article_name: data.article_name,
      article_name_tk: data.article_name_tk || null,
      cost_per_unit: parseFloat(data.cost_per_unit) || 0,
      item_type: data.item_type || 'Article',
      category: data.category || null,
      master_category: data.master_category || null,
      combo: data.combo ?? false,
      is_active: data.is_active ?? true,
      created_at: data.created_at,
      updated_at: data.updated_at,
    };

    // Log audit action with old and new values
    const userId = await getCurrentUserId();
    const updatedFields = Object.keys(updates);
    const oldValues: Record<string, any> = {};
    const newValues: Record<string, any> = {};

    updatedFields.forEach((field) => {
      if (oldData) {
        oldValues[field] = field === 'cost_per_unit' 
          ? parseFloat(oldData[field] || 0) 
          : oldData[field];
      }
      newValues[field] = updates[field as keyof typeof updates];
    });

    await logAction(userId, 'UPDATE', 'article', id, {
      entity_name: result.article_name,
      entity_summary: `Article: ${result.article_name}`,
      old_values: oldValues,
      new_values: newValues,
      updated_fields: updatedFields,
      affected_fields: updatedFields,
    });

    return result;
  } catch (error) {
    console.error('Failed to update article:', error);
    throw error;
  }
};

/**
 * Toggle article active status (inactivate/reactivate)
 */
export const toggleArticleStatus = async (id: string, isActive: boolean): Promise<ArticleRecord> => {
  try {
    const { data, error } = await supabase
      .from('articles')
      .update({ is_active: isActive })
      .eq('id', id)
      .select()
      .single();

    if (error) {
      console.error('Error toggling article status:', error);
      throw error;
    }

    const result = {
      id: data.id,
      article_name: data.article_name,
      cost_per_unit: parseFloat(data.cost_per_unit) || 0,
      item_type: data.item_type || 'Article',
      category: data.category || null,
      is_active: data.is_active ?? true,
      created_at: data.created_at,
      updated_at: data.updated_at,
    };

    // Log audit action with status change details
    const userId = await getCurrentUserId();
    await logAction(userId, 'STATUS_CHANGE', 'article', id, {
      entity_name: result.article_name,
      entity_summary: `Article: ${result.article_name}`,
      previous_status: !isActive,
      new_status: isActive,
      affected_fields: ['is_active'],
    });

    return result;
  } catch (error) {
    console.error('Failed to toggle article status:', error);
    throw error;
  }
};

/**
 * Delete an article after checking for foreign key references
 */
export const deleteArticle = async (id: string): Promise<void> => {
  try {
    // First, fetch the article to get its name for error messages
    const { data: articleData, error: fetchError } = await supabase
      .from('articles')
      .select('article_name')
      .eq('id', id)
      .single();

    if (fetchError || !articleData) {
      throw new Error('Article not found');
    }

    const articleName = articleData.article_name;

    // Check for foreign key references in all tables
    const referenceChecks = await Promise.all([
      // Check district_beneficiary_entries
      supabase
        .from('district_beneficiary_entries')
        .select('id', { count: 'exact', head: true })
        .eq('article_id', id),
      // Check public_beneficiary_entries
      supabase
        .from('public_beneficiary_entries')
        .select('id', { count: 'exact', head: true })
        .eq('article_id', id),
      // Check institutions_beneficiary_entries
      supabase
        .from('institutions_beneficiary_entries')
        .select('id', { count: 'exact', head: true })
        .eq('article_id', id),
      // Check order_entries
      supabase
        .from('order_entries')
        .select('id', { count: 'exact', head: true })
        .eq('article_id', id),
      // Check fund_request_articles
      supabase
        .from('fund_request_articles')
        .select('id', { count: 'exact', head: true })
        .eq('article_id', id),
    ]);

    const [
      { count: districtCount },
      { count: publicCount },
      { count: institutionsCount },
      { count: orderCount },
      { count: fundRequestCount },
    ] = referenceChecks.map((result) => ({ count: result.count || 0 }));

    // Build error message if any references exist
    const references: string[] = [];
    if (districtCount > 0) references.push(`${districtCount} district ${districtCount === 1 ? 'entry' : 'entries'}`);
    if (publicCount > 0) references.push(`${publicCount} public ${publicCount === 1 ? 'entry' : 'entries'}`);
    if (institutionsCount > 0) references.push(`${institutionsCount} institution ${institutionsCount === 1 ? 'entry' : 'entries'}`);
    if (orderCount > 0) references.push(`${orderCount} order ${orderCount === 1 ? 'entry' : 'entries'}`);
    if (fundRequestCount > 0) references.push(`${fundRequestCount} fund request ${fundRequestCount === 1 ? 'entry' : 'entries'}`);

    if (references.length > 0) {
      const errorMessage = `Cannot delete article '${articleName}'. It is currently being used in: ${references.join(', ')}.`;
      throw new Error(errorMessage);
    }

    // No references found, proceed with deletion
    const { error: deleteError } = await supabase
      .from('articles')
      .delete()
      .eq('id', id);

    if (deleteError) {
      console.error('Error deleting article:', deleteError);
      throw deleteError;
    }

    // Log audit action
    const userId = await getCurrentUserId();
    await logAction(userId, 'DELETE', 'article', id, {
      entity_name: articleName,
      entity_summary: `Article: ${articleName}`,
    });
  } catch (error) {
    console.error('Failed to delete article:', error);
    throw error;
  }
};
