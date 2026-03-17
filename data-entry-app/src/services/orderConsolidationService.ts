import { supabase, withTimeoutAndRetry } from '../lib/supabase';
import { fetchDistrictBeneficiaryEntriesGrouped } from './districtBeneficiaryService';
import { fetchInstitutionBeneficiaryEntriesGrouped } from './institutionBeneficiaryService';
import { fetchAllArticles } from './articlesService';
import type { MasterEntryRecord, ArticleSelection } from '../data/mockData';
import type { ArticleOrderSummary } from './orderService';

export interface ConsolidatedArticle {
  articleId: string;
  articleName: string;
  itemType?: string; // 'Article', 'Aid', or 'Project'
  totalQuantity: number;
  breakdown: {
    district: number;
    public: number;
    institutions: number;
  };
  totalValue: number;
  // Add order tracking fields
  quantityOrdered?: number;
  quantityReceived?: number;
  quantityPending?: number;
  orderSummary?: ArticleOrderSummary;
}

export interface OrderConsolidation {
  articles: ConsolidatedArticle[];
  totalArticles: number;
  totalValue: number;
}

/**
 * Split article name by "+" symbol and normalize each part
 * Normalizes to title case for case-insensitive matching
 */
function splitAndNormalizeArticleName(articleName: string): string[] {
  return articleName
    .split('+')
    .map(name => name.trim())
    .filter(name => name.length > 0)
    .map(name => {
      // Normalize to title case for consistent matching
      return name.split(' ')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
        .join(' ');
    });
}

/**
 * Fetch all entries from all beneficiary types and consolidate articles
 */
export const getConsolidatedOrders = async (): Promise<OrderConsolidation> => {
  const startTime = Date.now();
  console.debug('getConsolidatedOrders: Starting consolidation');
  
  try {
    // Fetch all articles to get article names
    const allArticles = await fetchAllArticles(true);
    const articleMapById = new Map(allArticles.map(a => [a.id, a]));
    
    // Helper to get article name
    const getArticleName = (articleId: string): string => {
      const article = articleMapById.get(articleId);
      return article?.article_name || articleId;
    };
    
    // Helper to get article item type
    const getArticleItemType = (articleId: string): string | undefined => {
      const article = articleMapById.get(articleId);
      return article?.item_type;
    };
    
    // Fetch district entries from database
    const districtRecords = await fetchDistrictBeneficiaryEntriesGrouped();
    
    // Fetch public entries from database
    const publicStartTime = Date.now();
    console.debug('getConsolidatedOrders: Fetching public entries');
    let publicData = null;
    let publicError = null;
    
    try {
      const result = await withTimeoutAndRetry(async () => {
        const { data, error } = await supabase
          .from('public_beneficiary_entries')
          .select(`
            id,
            application_number,
            name,
            aadhar_number,
            is_handicapped,
            address,
            mobile,
            article_id,
            quantity,
            total_amount,
            notes,
            status,
            created_at
          `);
        
        if (error) {
          throw error;
        }
        return data;
      }, 1, 15000); // 1 retry, 15 second timeout
      
      publicData = result;
      const duration = Date.now() - publicStartTime;
      console.debug(`getConsolidatedOrders: Public entries fetched in ${duration}ms, count: ${publicData?.length || 0}`);
    } catch (error: any) {
      publicError = error;
      const duration = Date.now() - publicStartTime;
      console.error(`getConsolidatedOrders: Failed to fetch public entries after ${duration}ms:`, publicError);
    }

    // Transform public entries to MasterEntryRecord format
    const publicRecords: MasterEntryRecord[] = (publicData || []).map((entry: any) => ({
      id: entry.id,
      applicationNumber: entry.application_number || '',
      beneficiaryType: 'public' as const,
      createdAt: entry.created_at,
      aadharNumber: entry.aadhar_number,
      name: entry.name,
      handicapped: entry.is_handicapped,
      address: entry.address,
      mobile: entry.mobile,
      articleId: entry.article_id,
      quantity: entry.quantity,
      costPerUnit: entry.quantity > 0 ? (entry.total_amount / entry.quantity) : 0,
      totalValue: entry.total_amount,
      comments: entry.notes || '',
    }));
    
    // Fetch institutions entries from database
    const institutionsRecords = await fetchInstitutionBeneficiaryEntriesGrouped();
    
    // Consolidate articles by normalized split name (not article ID)
    const consolidatedMap = new Map<string, ConsolidatedArticle>();
    
    // Helper function to add split items to consolidated map
    const addSplitItemsToMap = (
      articleName: string,
      quantity: number,
      totalValue: number,
      beneficiaryType: 'district' | 'public' | 'institutions',
      itemType?: string
    ) => {
      const splitNames = splitAndNormalizeArticleName(articleName);
      
      splitNames.forEach((splitName) => {
        const key = splitName; // Use normalized split name as key
        
        if (!consolidatedMap.has(key)) {
          consolidatedMap.set(key, {
            articleId: splitName, // Use normalized split name as articleId
            articleName: splitName,
            itemType: itemType,
            totalQuantity: 0,
            breakdown: {
              district: 0,
              public: 0,
              institutions: 0,
            },
            totalValue: 0,
          });
        }
        
        const consolidated = consolidatedMap.get(key)!;
        // Each split item gets the full quantity (not divided)
        consolidated.totalQuantity += quantity;
        consolidated.breakdown[beneficiaryType] += quantity;
        // Distribute totalValue proportionally (or could be full value per split item)
        // For now, we'll distribute it equally among split items
        const valuePerItem = totalValue / splitNames.length;
        consolidated.totalValue += valuePerItem;
      });
    };
    
    // Process district entries
    districtRecords.forEach((record) => {
      if (record.selectedArticles) {
        record.selectedArticles.forEach((article: ArticleSelection) => {
          const articleName = article.articleName || getArticleName(article.articleId);
          const itemType = getArticleItemType(article.articleId);
          addSplitItemsToMap(articleName, article.quantity, article.totalValue, 'district', itemType);
        });
      }
    });
    
    // Process public entries
    publicRecords.forEach((record) => {
      if (record.articleId && record.quantity) {
        const articleName = getArticleName(record.articleId);
        const itemType = getArticleItemType(record.articleId);
        addSplitItemsToMap(articleName, record.quantity || 0, record.totalValue || 0, 'public', itemType);
      }
    });
    
    // Process institutions entries
    institutionsRecords.forEach((record) => {
      if (record.selectedArticles) {
        record.selectedArticles.forEach((article: ArticleSelection) => {
          const articleName = article.articleName || getArticleName(article.articleId);
          const itemType = getArticleItemType(article.articleId);
          addSplitItemsToMap(articleName, article.quantity, article.totalValue, 'institutions', itemType);
        });
      }
    });
    
    // Convert map to array and sort by article name
    const articles = Array.from(consolidatedMap.values()).sort((a, b) =>
      a.articleName.localeCompare(b.articleName)
    );
    
    // Calculate totals
    const totalArticles = articles.length;
    const totalValue = articles.reduce((sum, article) => sum + article.totalValue, 0);
    
    const duration = Date.now() - startTime;
    const result = {
      articles,
      totalArticles,
      totalValue,
    };
    console.debug(`getConsolidatedOrders: Consolidation completed in ${duration}ms, articles: ${result.articles.length}, totalValue: ${totalValue}`);
    return result;
  } catch (error) {
    const duration = Date.now() - startTime;
    console.error(`getConsolidatedOrders: Failed after ${duration}ms:`, error);
    throw error;
  }
};

// Update the function to include order data
export const getConsolidatedOrdersWithTracking = async (): Promise<OrderConsolidation> => {
  const startTime = Date.now();
  console.debug('getConsolidatedOrdersWithTracking: Starting fetch with tracking');
  
  try {
    // First get the consolidated orders (needed quantity split by "+")
    const consolidation = await getConsolidatedOrders();

    // Build ordered/received totals using the same split-by-"+" logic as needed quantity.
    // This avoids mismatches where master has combo names but order entries are split components.
    const orderedBySplitName = new Map<string, number>();
    const receivedBySplitName = new Map<string, number>();

    const { data: orderEntries, error: orderError } = await withTimeoutAndRetry(async () => {
      const { data, error } = await supabase
        .from('order_entries')
        .select(`
          quantity_ordered,
          status,
          articles:article_id (
            article_name
          )
        `);
      if (error) throw error;
      return { data, error: null };
    }, 1, 15000);

    if (orderError) {
      throw orderError;
    }

    (orderEntries || []).forEach((entry: any) => {
      if (entry.status === 'cancelled') return;

      const quantityOrdered = Number(entry.quantity_ordered || 0);
      if (!Number.isFinite(quantityOrdered) || quantityOrdered <= 0) return;

      const articleName = entry.articles?.article_name || '';
      if (!articleName) return;

      const splitNames = splitAndNormalizeArticleName(articleName);
      splitNames.forEach((splitName) => {
        orderedBySplitName.set(
          splitName,
          (orderedBySplitName.get(splitName) || 0) + quantityOrdered
        );

        if (entry.status === 'received') {
          receivedBySplitName.set(
            splitName,
            (receivedBySplitName.get(splitName) || 0) + quantityOrdered
          );
        }
      });
    });

    // Map each consolidated article to its split-aware order data
    const articlesWithOrders = consolidation.articles.map(article => {
      const splitName = article.articleId; // normalized split token
      const totalQuantityOrdered = orderedBySplitName.get(splitName) || 0;
      const totalQuantityReceived = receivedBySplitName.get(splitName) || 0;
      const quantityPending = article.totalQuantity - totalQuantityOrdered;
      
      return {
        ...article,
        quantityOrdered: totalQuantityOrdered,
        quantityReceived: totalQuantityReceived,
        quantityPending: quantityPending,
        orderSummary: undefined, // Can't use single summary since we're aggregating multiple
      };
    });
    
    const duration = Date.now() - startTime;
    console.debug(`getConsolidatedOrdersWithTracking: Completed in ${duration}ms, articles: ${articlesWithOrders.length}`);
    
    return {
      articles: articlesWithOrders,
      totalArticles: consolidation.totalArticles,
      totalValue: consolidation.totalValue,
    };
  } catch (error) {
    const duration = Date.now() - startTime;
    console.error(`getConsolidatedOrdersWithTracking: Failed after ${duration}ms:`, error);
    throw error;
  }
};
