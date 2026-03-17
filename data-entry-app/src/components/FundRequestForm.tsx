import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Save, Loader2, Plus, Trash2, X, CheckCircle2 } from 'lucide-react';
import {
  fetchFundRequestById,
  createFundRequest,
  updateFundRequest,
  type FundRequest,
  type FundRequestRecipient,
} from '../services/fundRequestService';
import { fetchAllArticles, createArticle, toggleArticleStatus, type ArticleRecord } from '../services/articlesService';
import { getConsolidatedOrders } from '../services/orderConsolidationService';
import {
  fetchDistrictBeneficiariesForDropdown,
  fetchPublicBeneficiariesForDropdown,
  fetchInstitutionBeneficiariesForDropdown,
  fetchOthersBeneficiariesForDropdown,
  fetchUsedBeneficiariesForFundRequest,
  type BeneficiaryDropdownOption,
} from '../services/beneficiaryService';
import { fetchDistricts } from '../services/districtsService';
import type { District } from '../data/mockData';
import { useNotifications } from '../contexts/NotificationContext';
import { CURRENCY_SYMBOL } from '../constants/currency';
import MultiSelectArticles from './MultiSelectArticles';
import type { ArticleSelection } from '../data/mockData';
import {
  saveFundRequestDraft,
  loadFundRequestDraft,
  clearFundRequestDraft,
  formatDraftTimestamp,
} from '../utils/autoSave';

interface RecipientFormData extends Omit<FundRequestRecipient, 'id' | 'fund_request_id' | 'created_at'> {
  beneficiaryType?: 'District' | 'Public' | 'Institutions' | 'Others';
  beneficiaryOptions?: BeneficiaryDropdownOption[];
  loadingBeneficiaries?: boolean;
  selectedDistrictId?: string;
}

const isValidUUID = (value?: string): boolean => {
  if (!value) return false;
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
};

const getBeneficiaryLoadKey = (
  type: 'District' | 'Public' | 'Institutions' | 'Others',
  aidType?: string,
  districtId?: string
): string => `${type}::${(aidType || '').trim().toLowerCase()}::${districtId || ''}`;

const getAppNumberFromDisplay = (value: string): string => {
  const match = value.match(/^([^-]+)/);
  return match ? match[1].trim() : '';
};

const getInstitutionAidKey = (value: string): string => {
  const parts = value.split(' - ');
  const appNo = (parts[0] || '').trim().toLowerCase();
  const aidName = (parts[1] || '').trim().toLowerCase();
  if (appNo && aidName) return `${appNo}::${aidName}`;
  return value.trim().toLowerCase();
};

const getDistrictAidKey = (value: string): string => {
  const parts = value.split(' - ').map((p) => p.trim()).filter(Boolean);
  const appNo = (parts[0] || '').toLowerCase();
  const aidName = (parts[1] || '').toLowerCase();
  const amountRaw = (parts[2] || '').replace(/[^\d.]/g, '');
  const amount = amountRaw ? String(Number(amountRaw)) : '';
  const notes = parts.length > 3 ? parts.slice(3).join(' - ').toLowerCase() : '';
  if (!appNo) return value.trim().toLowerCase();
  return `${appNo}::${aidName}::${amount}::${notes}`;
};

const getDistrictAidBaseKey = (value: string): string => {
  const parts = value.split(' - ').map((p) => p.trim()).filter(Boolean);
  const appNo = (parts[0] || '').toLowerCase();
  const aidName = (parts[1] || '').toLowerCase();
  if (!appNo) return value.trim().toLowerCase();
  return `${appNo}::${aidName}`;
};

const getTrackingKey = (
  type: 'District' | 'Public' | 'Institutions' | 'Others' | undefined,
  displayValue: string
): string => {
  if (!displayValue) return '';
  if (type === 'District') return getDistrictAidKey(displayValue);
  if (type === 'Institutions') return displayValue;
  return getAppNumberFromDisplay(displayValue);
};

const FundRequestForm: React.FC = () => {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const { showError, showSuccess } = useNotifications();
  const [fundRequestType, setFundRequestType] = useState<'Aid' | 'Article'>('Aid');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [articles, setArticles] = useState<ArticleRecord[]>([]);
  const realArticleIdByNameRef = useRef<Map<string, string>>(new Map());

  // Form state
  const [formData, setFormData] = useState<Partial<FundRequest>>({
    fund_request_type: 'Aid',
    status: 'draft',
    total_amount: 0,
  });

  // Recipients (for Aid)
  const [recipients, setRecipients] = useState<RecipientFormData[]>([]);

  // Track selected beneficiaries in current session (key varies by type)
  const [selectedBeneficiaries, setSelectedBeneficiaries] = useState<Set<string>>(new Set());

  // Track used beneficiaries from saved fund requests
  const [usedBeneficiaries, setUsedBeneficiaries] = useState<Set<string>>(new Set());

  // Beneficiary data cache
  const [beneficiaryCache, setBeneficiaryCache] = useState<{
    District?: BeneficiaryDropdownOption[];
    Public?: BeneficiaryDropdownOption[];
    Institutions?: BeneficiaryDropdownOption[];
    Others?: BeneficiaryDropdownOption[];
  }>({});

  // Articles (for Article)
  const [selectedArticles, setSelectedArticles] = useState<ArticleSelection[]>([]);
  const [gstNumber, setGstNumber] = useState<string>('');
  const [supplierName, setSupplierName] = useState<string>('');
  const [supplierAddress, setSupplierAddress] = useState<string>('');
  const [supplierCity, setSupplierCity] = useState<string>('');
  const [supplierState, setSupplierState] = useState<string>('');
  const [supplierPincode, setSupplierPincode] = useState<string>('');
  const [articleDetails, setArticleDetails] = useState<Map<string, {
    beneficiary?: string;
    gst_no?: string;
    price_including_gst?: number;
    supplier_article_name?: string;
    cheque_in_favour?: string;
    cheque_no?: string;
  }>>(new Map());

  // Validation errors
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Aid type dropdown
  const [aidArticles, setAidArticles] = useState<ArticleRecord[]>([]);
  const [loadingAidArticles, setLoadingAidArticles] = useState(false);

  // Districts (for district filter in Aid)
  const [districts, setDistricts] = useState<District[]>([]);
  const [loadingDistricts, setLoadingDistricts] = useState(false);
  const beneficiaryRequestCacheRef = useRef<Map<string, BeneficiaryDropdownOption[]>>(new Map());

  // Auto-save refs
  const isInitialMount = useRef(true);
  const autoSaveTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const hasRestoredDraft = useRef(false);
  const savedDraftRef = useRef<ReturnType<typeof loadFundRequestDraft>>(null);

  // Draft notification state
  const [draftNotification, setDraftNotification] = useState<{
    isOpen: boolean;
    timestamp: string;
  }>({
    isOpen: false,
    timestamp: '',
  });
  const draftNotificationTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const showDraftRestoredNotification = (timestamp: number) => {
    const formattedTimestamp = formatDraftTimestamp(timestamp);
    setDraftNotification({
      isOpen: true,
      timestamp: formattedTimestamp,
    });

    if (draftNotificationTimeoutRef.current) {
      clearTimeout(draftNotificationTimeoutRef.current);
    }
    draftNotificationTimeoutRef.current = setTimeout(() => {
      setDraftNotification({ isOpen: false, timestamp: '' });
    }, 10000);
  };

  const restoreDraftState = (draft: NonNullable<ReturnType<typeof loadFundRequestDraft>>) => {
    setFundRequestType(draft.fundRequestType);
    setFormData(draft.formData);
    const restoredRecipients: RecipientFormData[] = (draft.recipients || []).map(r => ({
      beneficiaryType: r.beneficiaryType,
      recipient_name: r.recipient_name || '',
      beneficiary: r.beneficiary || '',
      name_of_beneficiary: r.name_of_beneficiary || '',
      name_of_institution: r.name_of_institution || '',
      details: r.details || '',
      fund_requested: r.fund_requested || 0,
      aadhar_number: r.aadhar_number || '',
      address: r.address || '',
      cheque_in_favour: r.cheque_in_favour || '',
      cheque_no: r.cheque_no || '',
      notes: r.notes || '',
      district_name: r.district_name,
    }));
    setRecipients(restoredRecipients);
    setSelectedArticles(draft.selectedArticles || []);
    setGstNumber(draft.gstNumber || '');
    setSupplierName(draft.supplierName || '');
    setSupplierAddress(draft.supplierAddress || '');
    setSupplierCity(draft.supplierCity || '');
    setSupplierState(draft.supplierState || '');
    setSupplierPincode(draft.supplierPincode || '');

    if (draft.articleDetails && draft.articleDetails.length > 0) {
      setArticleDetails(new Map(draft.articleDetails));
    }
    if (draft.selectedBeneficiaries && draft.selectedBeneficiaries.length > 0) {
      setSelectedBeneficiaries(new Set(draft.selectedBeneficiaries));
    }
    showDraftRestoredNotification(draft.timestamp);
  };

  const buildDraftData = () => ({
    fundRequestType,
    formData,
    recipients: recipients.map(r => ({
      beneficiaryType: r.beneficiaryType,
      recipient_name: r.recipient_name || '',
      beneficiary: r.beneficiary || '',
      name_of_beneficiary: r.name_of_beneficiary || '',
      name_of_institution: r.name_of_institution || '',
      details: r.details || '',
      fund_requested: r.fund_requested || 0,
      aadhar_number: r.aadhar_number || '',
      address: r.address || '',
      cheque_in_favour: r.cheque_in_favour || '',
      cheque_no: r.cheque_no || '',
      notes: r.notes || '',
      district_name: r.district_name,
    })),
    selectedArticles,
    gstNumber,
    supplierName,
    supplierAddress,
    supplierCity,
    supplierState,
    supplierPincode,
    articleDetails: Array.from(articleDetails.entries()),
    selectedBeneficiaries: Array.from(selectedBeneficiaries),
  });

  // Restore draft on mount (only for new forms)
  useEffect(() => {
    if (!id && !hasRestoredDraft.current) {
      const draft = loadFundRequestDraft();
      if (draft) {
        restoreDraftState(draft);
        hasRestoredDraft.current = true;
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Function to clear draft
  const handleClearDraft = () => {
    // Clear timeout if still running
    if (draftNotificationTimeoutRef.current) {
      clearTimeout(draftNotificationTimeoutRef.current);
      draftNotificationTimeoutRef.current = null;
    }
    clearFundRequestDraft();
    savedDraftRef.current = null;
    setDraftNotification({ isOpen: false, timestamp: '' });
    showSuccess('Draft cleared.');
  };

  // Function to close notification
  const handleCloseDraftNotification = () => {
    // Clear timeout if still running
    if (draftNotificationTimeoutRef.current) {
      clearTimeout(draftNotificationTimeoutRef.current);
      draftNotificationTimeoutRef.current = null;
    }
    setDraftNotification({ isOpen: false, timestamp: '' });
  };

  useEffect(() => {
    loadArticles();
    loadUsedBeneficiaries();
    if (fundRequestType === 'Aid') {
      loadAidArticles();
      loadDistricts();
    }
    if (id) {
      loadFundRequest();
    }
    isInitialMount.current = false;
  }, [id]);

  useEffect(() => {
    if (fundRequestType === 'Aid') {
      loadAidArticles();
    }
    // Reload articles when fund request type changes to filter correctly
    loadArticles();
  }, [fundRequestType]);

  // Auto-fill supplier state as "Tamil Nadu" when Fund Request type is Article
  useEffect(() => {
    if (fundRequestType === 'Article' && !supplierState) {
      setSupplierState('Tamil Nadu');
    }
  }, [fundRequestType, supplierState]);

  // Set default comments for Article type when form loads
  useEffect(() => {
    if (fundRequestType === 'Article' && !id && !formData.notes) {
      setFormData(prev => ({
        ...prev,
        notes: 'Purchase order issued with reference to: \nDelivery Period - Within a Week.\nPayment Terms - Immediate after delivery.\nTransport Cost - Inclusive.',
      }));
    }
  }, [fundRequestType, id]);

  // Reload beneficiaries when aid_type changes
  useEffect(() => {
    if (fundRequestType === 'Aid' && formData.aid_type) {
      // Clear cache and reload beneficiaries once per unique filter key
      setBeneficiaryCache({});
      beneficiaryRequestCacheRef.current.clear();
      const seen = new Set<string>();
      recipients.forEach((recipient, index) => {
        if (!recipient?.beneficiaryType) return;
        const safeDistrictId =
          recipient.beneficiaryType === 'District' && isValidUUID(recipient.selectedDistrictId)
            ? recipient.selectedDistrictId
            : undefined;
        const key = getBeneficiaryLoadKey(recipient.beneficiaryType, formData.aid_type, safeDistrictId);
        if (seen.has(key)) return;
        seen.add(key);
        void loadBeneficiaries(recipient.beneficiaryType, index, safeDistrictId);
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formData.aid_type]);

  // Load used beneficiaries from saved fund requests
  const loadUsedBeneficiaries = async () => {
    try {
      const used = await fetchUsedBeneficiariesForFundRequest(id || undefined);
      setUsedBeneficiaries(used);
    } catch (error) {
      console.error('Failed to load used beneficiaries:', error);
      // Don't show error to user, just continue without filtering
    }
  };

  // Load Aid articles for dropdown
  const loadAidArticles = async () => {
    try {
      setLoadingAidArticles(true);
      const allArticles = await fetchAllArticles(true);
      const aidArticlesList = allArticles.filter(article => article.item_type === 'Aid');
      setAidArticles(aidArticlesList);
    } catch (error) {
      console.error('Failed to load Aid articles:', error);
      // Don't show error to user, just continue
    } finally {
      setLoadingAidArticles(false);
    }
  };

  // Load districts
  const loadDistricts = async () => {
    try {
      setLoadingDistricts(true);
      const fetchedDistricts = await fetchDistricts();
      setDistricts(fetchedDistricts);
    } catch (error) {
      console.error('Failed to load districts:', error);
      // Don't show error to user, just continue
    } finally {
      setLoadingDistricts(false);
    }
  };

  useEffect(() => {
    if (fundRequestType === 'Article') {
      calculateArticleTotals();
    } else {
      calculateAidTotal();
    }
  }, [selectedArticles, articleDetails, recipients, fundRequestType]);

  // Auto-save on state changes (debounced)
  useEffect(() => {
    // Don't save on initial mount
    if (isInitialMount.current) {
      return;
    }

    // Don't save if form is empty (no meaningful data)
    const hasData = 
      (fundRequestType === 'Aid' && recipients.length > 0) ||
      (fundRequestType === 'Article' && selectedArticles.length > 0) ||
      formData.aid_type ||
      gstNumber ||
      supplierName ||
      supplierAddress ||
      supplierCity ||
      supplierState ||
      supplierPincode ||
      formData.notes;

    if (!hasData) {
      return;
    }

    // Clear existing timeout
    if (autoSaveTimeoutRef.current) {
      clearTimeout(autoSaveTimeoutRef.current);
    }

    // Debounce save (500ms)
    autoSaveTimeoutRef.current = setTimeout(() => {
      try {
        saveFundRequestDraft(buildDraftData(), id);
      } catch (error) {
        console.error('Error auto-saving draft:', error);
      }
    }, 500);

    // Cleanup timeout on unmount
    return () => {
      if (autoSaveTimeoutRef.current) {
        clearTimeout(autoSaveTimeoutRef.current);
      }
    };
  }, [
    fundRequestType,
    formData,
    recipients,
    selectedArticles,
    gstNumber,
    supplierName,
    supplierAddress,
    supplierCity,
    supplierState,
    supplierPincode,
    articleDetails,
    selectedBeneficiaries,
    id,
  ]);

  const normalizeArticleName = (name: string): string =>
    name.trim().toLowerCase().replace(/\s+/g, ' ');

  const isVirtualSplitId = (id: string): boolean => id.startsWith('split::');

  const loadArticles = async () => {
    try {
      const data = await fetchAllArticles(true);
      // Filter articles by item_type based on fund request type
      if (fundRequestType === 'Article') {
        // For Article fund requests, use the consolidated order list (split names).
        // This keeps the dropdown aligned with Order Management.
        let consolidatedArticles: { articleName: string; itemType?: string }[] = [];
        try {
          const consolidatedOrders = await getConsolidatedOrders();
          consolidatedArticles = consolidatedOrders.articles.filter(
            article => article.itemType === 'Article'
          );
        } catch (consolidationError) {
          console.error('Failed to load consolidated orders for Fund Request:', consolidationError);
          // Fallback to empty list; caller will still have real articles mapping
          consolidatedArticles = [];
        }

        // Map real articles by normalized name for fast lookup
        const realArticles = data.filter(a => a.item_type === 'Article');
        const realByName = new Map<string, ArticleRecord>();
        realArticles.forEach(article => {
          realByName.set(normalizeArticleName(article.article_name), article);
        });
        realArticleIdByNameRef.current = new Map(
          Array.from(realByName.entries()).map(([key, article]) => [key, article.id])
        );

        if (consolidatedArticles.length === 0) {
          // If no consolidation data is available, fall back to real articles
          setArticles(realArticles);
        } else {
          // Build dropdown list from consolidated order names
          const dropdownArticles: ArticleRecord[] = consolidatedArticles.map((item) => {
            const normalizedName = normalizeArticleName(item.articleName);
            const existing = realByName.get(normalizedName);
            if (existing) return existing;

            // Virtual record for split names not in articles table (resolved on save)
          return {
            id: `split::${item.articleName}`,
            article_name: item.articleName,
            article_name_tk: undefined,
            cost_per_unit: 0,
            item_type: 'Article',
            category: undefined,
            combo: true,
            is_active: true,
          };
          });

          setArticles(dropdownArticles);
        }
      } else {
        // For Aid fund requests, show all articles (existing behavior)
        setArticles(data);
      }
    } catch (error) {
      console.error('Failed to load articles:', error);
      showError('Failed to load articles.');
    }
  };

  const loadFundRequest = async () => {
    if (!id) return;

    try {
      setLoading(true);
      const data = await fetchFundRequestById(id);
      if (data) {
        setFormData(data);
        setFundRequestType(data.fund_request_type);
        if (data.recipients) {
          const loadedRecipients = data.recipients.map(r => ({
            beneficiaryType: r.beneficiary_type,
            recipient_name: r.recipient_name,
            beneficiary: r.beneficiary,
            name_of_beneficiary: r.name_of_beneficiary,
            name_of_institution: r.name_of_institution,
            details: r.details,
            fund_requested: r.fund_requested,
            aadhar_number: r.aadhar_number,
            cheque_in_favour: r.cheque_in_favour,
            cheque_no: r.cheque_no,
            notes: r.notes,
            district_name: r.district_name,
          }));
          setRecipients(loadedRecipients);
          
          // Track beneficiaries from loaded data
          const loadedBeneficiaries = new Set<string>();
          loadedRecipients.forEach(r => {
            const key = getTrackingKey(r.beneficiaryType, r.beneficiary || '');
            if (key) loadedBeneficiaries.add(key);
          });
          setSelectedBeneficiaries(loadedBeneficiaries);
        }
        if (data.articles) {
          const articleSelections: ArticleSelection[] = data.articles.map((a) => ({
            articleId: a.article_id,
            articleName: a.article_name,
            quantity: a.quantity,
            costPerUnit: a.price_including_gst || a.unit_price, // Use price_including_gst as costPerUnit
            totalValue: a.value,
            supplier_article_name: a.supplier_article_name,
            cheque_in_favour: a.cheque_in_favour,
            description: a.description,
          }));
          setSelectedArticles(articleSelections);
          
          const detailsMap = new Map();
          data.articles.forEach(a => {
            detailsMap.set(a.article_id, {
              beneficiary: a.beneficiary,
              gst_no: a.gst_no,
              price_including_gst: a.price_including_gst,
              supplier_article_name: a.supplier_article_name,
              cheque_in_favour: a.cheque_in_favour,
              cheque_no: a.cheque_no,
            });
          });
          setArticleDetails(detailsMap);
        }
        // Load GST number and supplier fields for Article type
        if (data.fund_request_type === 'Article') {
          if (data.gst_number) setGstNumber(data.gst_number);
          if (data.supplier_name) setSupplierName(data.supplier_name);
          if (data.supplier_address) setSupplierAddress(data.supplier_address);
          if (data.supplier_city) setSupplierCity(data.supplier_city);
          if (data.supplier_state) setSupplierState(data.supplier_state);
          if (data.supplier_pincode) setSupplierPincode(data.supplier_pincode);
        }

        // If a local draft exists for this FR, prefer it over server state.
        const draft = loadFundRequestDraft(id);
        if (draft) {
          restoreDraftState(draft);
          hasRestoredDraft.current = true;
        }
      }
    } catch (error) {
      console.error('Failed to load fund request:', error);
      showError('Failed to load fund request.');
    } finally {
      setLoading(false);
    }
  };

  const loadBeneficiaries = async (type: 'District' | 'Public' | 'Institutions' | 'Others', recipientIndex: number, districtId?: string) => {
    // Get current aid_type for filtering
    const currentAidType = formData.aid_type;
    // Get selected district ID - use provided parameter or from current recipient state
    const currentRecipient = recipients[recipientIndex];
    const rawDistrictId = districtId !== undefined ? districtId : currentRecipient?.selectedDistrictId;
    const selectedDistrictId = type === 'District' && isValidUUID(rawDistrictId) ? rawDistrictId : undefined;
    const requestKey = getBeneficiaryLoadKey(type, currentAidType, selectedDistrictId);
    
    // Check cache first (but only if no aid_type filter and no district filter is applied)
    // When district is selected, we need individual entries with aid types, not grouped cache
    // Always skip cache when districtId is provided (for District type) or when aidType is provided
    const shouldUseCache = beneficiaryCache[type] && !currentAidType && !selectedDistrictId;

    const applyRecipientExclusions = (
      options: BeneficiaryDropdownOption[],
      recipient: RecipientFormData | undefined
    ): BeneficiaryDropdownOption[] => {
      const currentSelection = recipient?.beneficiary;
      let currentIdentifier: string | null = null;
      if (currentSelection) {
        currentIdentifier = getTrackingKey(type, currentSelection);
      }

      const allExcluded = new Set([...selectedBeneficiaries, ...usedBeneficiaries]);
      if (currentIdentifier) {
        allExcluded.delete(currentIdentifier);
      }

      return options.filter(option => {
        if (type === 'District') {
          const detailedKey = getDistrictAidKey(option.display_text);
          const baseKey = getDistrictAidBaseKey(option.display_text);
          if (allExcluded.has(detailedKey)) {
            return false;
          }

          if (allExcluded.has(baseKey)) {
            // Use base-key fallback only when there are no detailed-key matches
            // for this app+aid group (legacy rows without notes/details).
            const hasAnyDetailedMatchForSameBase = options.some((candidate) => {
              if (getDistrictAidBaseKey(candidate.display_text) !== baseKey) return false;
              return allExcluded.has(getDistrictAidKey(candidate.display_text));
            });

            if (!hasAnyDetailedMatchForSameBase) {
              return false;
            }
          }

          return true;
        }
        if (type === 'Institutions') {
          // For current in-form selections, exclude exact option only (allow multiple rows under same aid).
          if (selectedBeneficiaries.has(option.display_text)) {
            return false;
          }
          // In edit mode, allow options so legacy/incomplete rows can be recovered.
          if (id) {
            return true;
          }
          // In create mode, exclude already-used entries from other saved FRs by stable key.
          const usedInstitutionAidKeys = new Set(
            Array.from(usedBeneficiaries).map((value) => getInstitutionAidKey(value))
          );
          return !usedInstitutionAidKeys.has(getInstitutionAidKey(option.display_text));
        }
        return !allExcluded.has(option.application_number);
      });
    };

    const ensureCurrentSelectionVisible = (
      options: BeneficiaryDropdownOption[],
      recipient: RecipientFormData | undefined
    ): BeneficiaryDropdownOption[] => {
      const selectedValue = String(recipient?.beneficiary || '').trim();
      if (!selectedValue) return options;

      const alreadyPresent = options.some((opt) => opt.display_text === selectedValue);
      if (alreadyPresent) return options;

      const amount = Number(recipient?.fund_requested || 0);
      const appNo = getAppNumberFromDisplay(selectedValue) || selectedValue;

      return [
        {
          application_number: appNo,
          display_text: selectedValue,
          total_amount: amount,
          district_name: recipient?.district_name,
        },
        ...options,
      ];
    };

    const inferMissingBeneficiarySelection = (
      options: BeneficiaryDropdownOption[],
      recipient: RecipientFormData | undefined
    ): string | null => {
      if (!recipient || recipient.beneficiary) return null;
      const recipientName = String(recipient.recipient_name || recipient.name_of_beneficiary || '').trim().toLowerCase();
      const requested = Number(recipient.fund_requested || 0);
      if (!recipientName || requested <= 0) return null;

      const matches = options.filter((opt) => {
        const text = String(opt.display_text || '').toLowerCase();
        const amount = Number(opt.total_amount || 0);
        return text.includes(recipientName) && amount === requested;
      });

      return matches.length === 1 ? matches[0].display_text : null;
    };
    
    if (shouldUseCache) {
      // Only use cache if no aid_type filter and no district filter is applied
      // Filter out already selected beneficiaries (current session + saved)
      // Don't exclude current recipient's selection
      setRecipients(prev => {
        const currentRecipient = prev[recipientIndex];
        const filteredData = applyRecipientExclusions(beneficiaryCache[type]!, currentRecipient);
        const optionsWithCurrent = ensureCurrentSelectionVisible(filteredData, currentRecipient);
        const inferredBeneficiary = inferMissingBeneficiarySelection(optionsWithCurrent, currentRecipient);
        
        const updated = [...prev];
        updated[recipientIndex] = {
          ...updated[recipientIndex],
          beneficiaryOptions: optionsWithCurrent,
          ...(inferredBeneficiary ? { beneficiary: inferredBeneficiary } : {}),
          loadingBeneficiaries: false,
        };
        return updated;
      });
      return;
    }

    const cachedByRequestKey = beneficiaryRequestCacheRef.current.get(requestKey);
    if (cachedByRequestKey) {
      setRecipients(prev => {
        const updated = [...prev];
        const currentRecipient = prev[recipientIndex];
        const filteredData = applyRecipientExclusions(cachedByRequestKey, currentRecipient);
        const optionsWithCurrent = ensureCurrentSelectionVisible(filteredData, currentRecipient);
        const inferredBeneficiary = inferMissingBeneficiarySelection(optionsWithCurrent, currentRecipient);
        updated[recipientIndex] = {
          ...updated[recipientIndex],
          beneficiaryOptions: optionsWithCurrent,
          ...(inferredBeneficiary ? { beneficiary: inferredBeneficiary } : {}),
          loadingBeneficiaries: false,
        };
        return updated;
      });
      return;
    }

    // Set loading state
    setRecipients(prev => {
      const updated = [...prev];
      updated[recipientIndex] = {
        ...updated[recipientIndex],
        loadingBeneficiaries: true,
      };
      return updated;
    });

    try {
      let data: BeneficiaryDropdownOption[] = [];
      
      switch (type) {
        case 'District':
          data = await fetchDistrictBeneficiariesForDropdown(currentAidType, selectedDistrictId);
          break;
        case 'Public':
          data = await fetchPublicBeneficiariesForDropdown(currentAidType);
          break;
        case 'Institutions':
          data = await fetchInstitutionBeneficiariesForDropdown(currentAidType);
          break;
        case 'Others':
          data = await fetchOthersBeneficiariesForDropdown(currentAidType);
          break;
      }

      // Update cache (only if no aid_type filter and no district filter, otherwise cache is per filter)
      // Don't cache when district is selected because we want individual entries, not grouped
      if (!currentAidType && !selectedDistrictId) {
        setBeneficiaryCache(prev => ({ ...prev, [type]: data }));
      }
      beneficiaryRequestCacheRef.current.set(requestKey, data);

      // Filter out already selected beneficiaries (current session + saved)
      // Use functional update to get latest state
      setRecipients(prev => {
        const currentRecipient = prev[recipientIndex];
        const filteredData = applyRecipientExclusions(data, currentRecipient);
        const optionsWithCurrent = ensureCurrentSelectionVisible(filteredData, currentRecipient);
        const inferredBeneficiary = inferMissingBeneficiarySelection(optionsWithCurrent, currentRecipient);

        const updated = [...prev];
        updated[recipientIndex] = {
          ...updated[recipientIndex],
          beneficiaryOptions: optionsWithCurrent,
          ...(inferredBeneficiary ? { beneficiary: inferredBeneficiary } : {}),
          loadingBeneficiaries: false,
        };
        return updated;
      });
    } catch (error) {
      console.error(`Failed to load ${type} beneficiaries:`, error);
      showError(`Failed to load ${type} beneficiaries.`);
      setRecipients(prev => {
        const updated = [...prev];
        updated[recipientIndex] = {
          ...updated[recipientIndex],
          loadingBeneficiaries: false,
        };
        return updated;
      });
    }
  };

  const calculateAidTotal = () => {
    const total = recipients.reduce((sum, recipient) => sum + (recipient.fund_requested || 0), 0);
    setFormData(prev => ({ ...prev, total_amount: total }));
  };

  const calculateArticleTotals = () => {
    const updatedArticles = selectedArticles.map(article => {
      // For Article fund requests, use costPerUnit as price_including_gst
      const value = article.quantity * article.costPerUnit;
      return {
        ...article,
        totalValue: value,
      };
    });
    
    if (JSON.stringify(updatedArticles) !== JSON.stringify(selectedArticles)) {
      setSelectedArticles(updatedArticles);
    }
    
    const grandTotal = updatedArticles.reduce((sum, a) => sum + a.totalValue, 0);
    setFormData(prev => ({ ...prev, total_amount: grandTotal }));
  };

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (fundRequestType === 'Aid') {
      if (recipients.length === 0) {
        newErrors.recipients = 'At least one recipient is required';
      }
      
      recipients.forEach((recipient, index) => {
        if (!recipient.beneficiaryType) {
          newErrors[`beneficiary_type_${index}`] = 'Beneficiary type is required';
        }
        // Beneficiary is optional - can be saved without it (useful when editing existing records)
        if (!recipient.name_of_beneficiary && !recipient.recipient_name) {
          newErrors[`name_of_beneficiary_${index}`] = 'Name of beneficiary is required';
        }
        if (!recipient.fund_requested || recipient.fund_requested <= 0) {
          newErrors[`fund_requested_${index}`] = 'Fund requested must be greater than 0';
        }
        if (!recipient.name_of_institution) {
          newErrors[`name_of_institution_${index}`] = 'Name of Institution is required';
        }
        if (!recipient.aadhar_number) {
          newErrors[`aadhar_number_${index}`] = 'Aadhar number is required';
        } else if (!/^\d{12}$/.test(recipient.aadhar_number)) {
          newErrors[`aadhar_number_${index}`] = 'Aadhar number must be exactly 12 digits';
        }
        // Notes (Details) is mandatory for Aid
        if (!recipient.notes || recipient.notes.trim() === '') {
          newErrors[`notes_${index}`] = 'Details is required';
        }
        // cheque_in_favour and cheque_no are optional
      });
    } else {
      // Validate GST number and supplier fields for Article type
      if (!gstNumber || gstNumber.trim() === '') {
        newErrors.gst_number = 'GST number is required';
      }
      if (!supplierName || supplierName.trim() === '') {
        newErrors.supplier_name = 'Supplier name is required';
      }
      if (!supplierAddress || supplierAddress.trim() === '') {
        newErrors.supplier_address = 'Supplier address is required';
      }
      if (!supplierCity || supplierCity.trim() === '') {
        newErrors.supplier_city = 'Supplier city is required';
      }
      if (!supplierState || supplierState.trim() === '') {
        newErrors.supplier_state = 'Supplier state is required';
      }
      if (!supplierPincode || supplierPincode.trim() === '') {
        newErrors.supplier_pincode = 'Supplier pincode is required';
      }
      
      if (selectedArticles.length === 0) {
        newErrors.articles = 'At least one article is required';
      }
      
      selectedArticles.forEach((article, index) => {
        // For Article fund requests, validate costPerUnit (which is price_including_gst)
        if (!article.costPerUnit || article.costPerUnit <= 0) {
          newErrors[`price_${index}`] = 'Price including GST must be greater than 0';
        }
      });
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const resolveSplitArticleId = async (articleName: string): Promise<string> => {
    const normalizedName = normalizeArticleName(articleName);
    const existingId = realArticleIdByNameRef.current.get(normalizedName);
    if (existingId) {
      return existingId;
    }

    const created = await createArticle({
      article_name: articleName,
      cost_per_unit: 0,
      item_type: 'Article',
      combo: true,
    });

    // Keep split articles out of normal article pickers (used only for ordering)
    try {
      await toggleArticleStatus(created.id, false);
    } catch (error) {
      console.warn('Failed to mark split article inactive:', error);
    }

    realArticleIdByNameRef.current.set(normalizedName, created.id);
    return created.id;
  };

  const handleSave = async () => {
    if (!validateForm()) {
      showError('Please fix the errors in the form.');
      return;
    }

    try {
      // Persist immediate local backup before network save starts.
      saveFundRequestDraft(buildDraftData(), id);
      setSaving(true);

      const fundRequestData: Omit<FundRequest, 'id' | 'created_at' | 'updated_at'> = {
        fund_request_type: fundRequestType,
        fund_request_number: formData.fund_request_number || '',
        status: formData.status || 'draft',
        total_amount: formData.total_amount || 0,
        aid_type: fundRequestType === 'Aid' ? formData.aid_type : undefined,
        gst_number: fundRequestType === 'Article' ? gstNumber : undefined,
        supplier_name: fundRequestType === 'Article' ? supplierName : undefined,
        supplier_address: fundRequestType === 'Article' ? supplierAddress : undefined,
        supplier_city: fundRequestType === 'Article' ? supplierCity : undefined,
        supplier_state: fundRequestType === 'Article' ? supplierState : undefined,
        supplier_pincode: fundRequestType === 'Article' ? supplierPincode : undefined,
        notes: formData.notes,
      };

      if (fundRequestType === 'Aid') {
        if (id) {
          await updateFundRequest(id, {
            fundRequest: fundRequestData,
            recipients: recipients.map(r => ({
              beneficiary_type: r.beneficiaryType,
              recipient_name: r.recipient_name || r.name_of_beneficiary || '',
              beneficiary: r.beneficiary,
              name_of_beneficiary: r.name_of_beneficiary,
              name_of_institution: r.name_of_institution,
              details: r.details,
              fund_requested: r.fund_requested || 0,
              aadhar_number: r.aadhar_number,
              address: r.address,
              cheque_in_favour: r.cheque_in_favour,
              cheque_no: r.cheque_no,
              notes: r.notes,
              district_name: r.district_name,
            })),
          });
        } else {
          await createFundRequest({
            fundRequest: fundRequestData,
            recipients: recipients.map(r => ({
              beneficiary_type: r.beneficiaryType,
              recipient_name: r.recipient_name || r.name_of_beneficiary || '',
              beneficiary: r.beneficiary,
              name_of_beneficiary: r.name_of_beneficiary,
              name_of_institution: r.name_of_institution,
              details: r.details,
              fund_requested: r.fund_requested || 0,
              aadhar_number: r.aadhar_number,
              address: r.address,
              cheque_in_favour: r.cheque_in_favour,
              cheque_no: r.cheque_no,
              notes: r.notes,
              district_name: r.district_name,
            })),
          });
        }
      } else {
        const articlesData = await Promise.all(selectedArticles.map(async (article, index) => {
          const resolvedArticleId = isVirtualSplitId(article.articleId)
            ? await resolveSplitArticleId(article.articleName)
            : article.articleId;
          // Use values from ArticleSelection (cheque_in_favour, supplier_article_name)
          // and sync with articleDetails for price_including_gst
          const details = articleDetails.get(article.articleId) || { price_including_gst: 0 };
          
          return {
            article_id: resolvedArticleId,
            sl_no: index + 1, // Auto-generate SL.NO
            beneficiary: 'Dist & Public', // Auto-set beneficiary
            article_name: article.articleName,
            gst_no: gstNumber, // Use GST number from top field
            quantity: article.quantity,
            unit_price: article.costPerUnit,
            price_including_gst: article.costPerUnit, // Use costPerUnit as price_including_gst
            value: article.totalValue,
            cumulative: 0, // Remove cumulative calculation
            supplier_article_name: article.supplier_article_name || details.supplier_article_name,
            cheque_in_favour: article.cheque_in_favour || details.cheque_in_favour,
            cheque_no: details.cheque_no, // Still from articleDetails (not in ArticleRow yet)
            description: article.description,
          };
        }));

        if (id) {
          await updateFundRequest(id, {
            fundRequest: fundRequestData,
            articles: articlesData,
          });
        } else {
          await createFundRequest({
            fundRequest: fundRequestData,
            articles: articlesData,
          });
        }
      }

      // Clear draft after successful save
      clearFundRequestDraft(id);
      
      showSuccess(id ? 'Fund request updated successfully.' : 'Fund request created successfully.');
      navigate('/fund-request');
    } catch (error) {
      console.error('Failed to save fund request:', error);
      showError('Failed to save fund request. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const handleAddRecipient = (insertAfterIndex?: number) => {
    const sourceIndex = insertAfterIndex !== undefined ? insertAfterIndex : recipients.length - 1;
    const sourceRecipient = sourceIndex >= 0 ? recipients[sourceIndex] : undefined;

    const newRecipient: RecipientFormData = {
      beneficiaryType: sourceRecipient?.beneficiaryType,
      selectedDistrictId: sourceRecipient?.selectedDistrictId,
      district_name: sourceRecipient?.district_name,
      loadingBeneficiaries: !!sourceRecipient?.beneficiaryType,
      recipient_name: '',
      beneficiary: '',
      name_of_beneficiary: '',
      name_of_institution: '',
      details: '',
      fund_requested: 0,
      aadhar_number: '',
      cheque_in_favour: '',
      cheque_no: '',
      notes: '',
    };

    let newIndex = recipients.length;
    if (insertAfterIndex !== undefined) {
      // Insert after specific index
      const updated = [...recipients];
      newIndex = insertAfterIndex + 1;
      updated.splice(newIndex, 0, newRecipient);
      setRecipients(updated);
    } else {
      // Add to end
      setRecipients([...recipients, newRecipient]);
    }

    // Preload beneficiaries for the copied type/district so dropdown is ready.
    if (newRecipient.beneficiaryType) {
      const districtId =
        newRecipient.beneficiaryType === 'District' && isValidUUID(newRecipient.selectedDistrictId)
          ? newRecipient.selectedDistrictId
          : undefined;
      setTimeout(() => {
        void loadBeneficiaries(newRecipient.beneficiaryType!, newIndex, districtId);
      }, 0);
    }
  };

  const handleRemoveRecipient = (index: number) => {
    const recipientToRemove = recipients[index];
    // Remove beneficiary from tracking if it was selected
    if (recipientToRemove.beneficiary) {
      if (recipientToRemove.beneficiaryType === 'District' || recipientToRemove.beneficiaryType === 'Institutions') {
        setSelectedBeneficiaries(prev => {
          const updated = new Set(prev);
          const key = getTrackingKey(recipientToRemove.beneficiaryType, recipientToRemove.beneficiary!);
          if (key) updated.delete(key);
          return updated;
        });
      } else {
        const key = getTrackingKey(recipientToRemove.beneficiaryType, recipientToRemove.beneficiary);
        if (key) {
          setSelectedBeneficiaries(prev => {
            const updated = new Set(prev);
            updated.delete(key);
            return updated;
          });
        }
      }
    }
    setRecipients(recipients.filter((_, i) => i !== index));
  };

  const handleRecipientChange = (index: number, field: string, value: any) => {
    const updated = [...recipients];
    const oldRecipient = updated[index];
    updated[index] = { ...updated[index], [field]: value };
    setRecipients(updated);

    // Track beneficiary selection/deselection and auto-populate fund_requested
    if (field === 'beneficiary') {
      setSelectedBeneficiaries(prev => {
        const updatedSet = new Set(prev);
        
        // Remove old selection if it existed
        if (oldRecipient.beneficiary) {
          // For district beneficiaries use display text, institutions use app+aid key
          // For other types, extract app number from display text
          if (oldRecipient.beneficiaryType === 'District' || oldRecipient.beneficiaryType === 'Institutions') {
            const key = getTrackingKey(oldRecipient.beneficiaryType, oldRecipient.beneficiary);
            if (key) updatedSet.delete(key);
          } else {
            const key = getTrackingKey(oldRecipient.beneficiaryType, oldRecipient.beneficiary);
            if (key) updatedSet.delete(key);
          }
        }
        
        // Add new selection
        if (value) {
          const recipient = updated[index];
          
          // Auto-populate fund_requested from beneficiary option
          if (recipient.beneficiaryOptions) {
            const selectedOption = recipient.beneficiaryOptions.find(
              opt => opt.display_text === value
            );
            if (selectedOption) {
              // For district beneficiaries use display text, institutions use app+aid key
              // For other types, extract app number from display text
              if (recipient.beneficiaryType === 'District' || recipient.beneficiaryType === 'Institutions') {
                const key = getTrackingKey(recipient.beneficiaryType, value);
                if (key) updatedSet.add(key);
              } else {
                const key = getTrackingKey(recipient.beneficiaryType, value);
                if (key) updatedSet.add(key);
              }
              
              // Always sync fund_requested from selected beneficiary amount
              updated[index] = {
                ...updated[index],
                fund_requested: selectedOption.total_amount || 0,
              };
              
              // For District beneficiaries, set district_name from the option if available
              if (recipient.beneficiaryType === 'District' && selectedOption.district_name) {
                updated[index] = {
                  ...updated[index],
                  district_name: selectedOption.district_name,
                };
              }
              
              // Auto-fill name and aadhar_number for public beneficiaries
              if (recipient.beneficiaryType === 'Public') {
                const updates: Partial<RecipientFormData> = {};
                
                // Auto-fill name from beneficiary option
                if (selectedOption.name) {
                  updates.name_of_beneficiary = selectedOption.name;
                  updates.recipient_name = selectedOption.name;
                }
                
                // Auto-fill aadhar_number (always update, not just when empty)
                if (selectedOption.aadhar_number) {
                  updates.aadhar_number = selectedOption.aadhar_number;
                }
                
                if (Object.keys(updates).length > 0) {
                  updated[index] = {
                    ...updated[index],
                    ...updates,
                  };
                }
              }
              
              setRecipients(updated);
            }
          } else if (!value) {
            // Beneficiary cleared: clear auto-filled amount as well
            updated[index] = {
              ...updated[index],
              fund_requested: 0,
            };
            setRecipients(updated);
          }
        }
        
        return updatedSet;
      });
    }
  };

  // Keep dropdown options in sync after select/reselect so availability updates immediately.
  useEffect(() => {
    const seen = new Set<string>();
    recipients.forEach((recipient, idx) => {
      if (!recipient.beneficiaryType || recipient.loadingBeneficiaries) return;
      const safeDistrictId =
        recipient.beneficiaryType === 'District' && isValidUUID(recipient.selectedDistrictId)
          ? recipient.selectedDistrictId
          : undefined;
      const key = getBeneficiaryLoadKey(recipient.beneficiaryType, formData.aid_type, safeDistrictId);
      if (seen.has(key)) return;
      seen.add(key);
      void loadBeneficiaries(recipient.beneficiaryType, idx, safeDistrictId);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedBeneficiaries, usedBeneficiaries, formData.aid_type]);

  const handleBeneficiaryTypeChange = (index: number, type: 'District' | 'Public' | 'Institutions' | 'Others' | undefined) => {
    const updated = [...recipients];
    const oldRecipient = updated[index];
    
    // Remove old beneficiary from tracking if it existed
    if (oldRecipient.beneficiary) {
      // For district beneficiaries use display text, institutions use app+aid key
      // For other types, extract app number from display text
      if (oldRecipient.beneficiaryType === 'District' || oldRecipient.beneficiaryType === 'Institutions') {
        setSelectedBeneficiaries(prev => {
          const updatedSet = new Set(prev);
          const key = getTrackingKey(oldRecipient.beneficiaryType, oldRecipient.beneficiary!);
          if (key) updatedSet.delete(key);
          return updatedSet;
        });
      } else {
        const key = getTrackingKey(oldRecipient.beneficiaryType, oldRecipient.beneficiary);
        if (key) {
          setSelectedBeneficiaries(prev => {
            const updatedSet = new Set(prev);
            updatedSet.delete(key);
            return updatedSet;
          });
        }
      }
    }
    
    updated[index] = {
      ...updated[index],
      beneficiaryType: type,
      beneficiary: '', // Clear beneficiary when type changes
      beneficiaryOptions: undefined,
      selectedDistrictId: type === 'District' ? updated[index].selectedDistrictId : undefined, // Keep district if still District type
    };
    setRecipients(updated);

    if (type) {
      loadBeneficiaries(type, index);
    }
  };


  const handleArticlesChange = (newArticles: ArticleSelection[]) => {
    setSelectedArticles(newArticles);
    // Initialize details for new articles and sync cheque_in_favour and supplier_article_name
    const updatedDetails = new Map(articleDetails);
    newArticles.forEach(article => {
      const existing = updatedDetails.get(article.articleId) || {
        price_including_gst: 0,
        cheque_in_favour: undefined,
        supplier_article_name: undefined,
      };
      updatedDetails.set(article.articleId, {
        ...existing,
        price_including_gst: article.costPerUnit || existing.price_including_gst || 0,
        cheque_in_favour: article.cheque_in_favour || existing.cheque_in_favour,
        supplier_article_name: article.supplier_article_name || existing.supplier_article_name,
      });
    });
    setArticleDetails(updatedDetails);
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6 flex items-center gap-4">
        <button
          onClick={() => navigate('/fund-request')}
          className="p-2 text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            {id ? 'Edit Fund Request' : 'Create Fund Request'}
          </h1>
          <p className="text-gray-600 dark:text-gray-400 mt-1">
            {id ? 'Update fund request details' : 'Create a new fund request for Aid or Article'}
          </p>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
        {/* Type Selection */}
        <div className="mb-8 pb-6 border-b border-gray-200 dark:border-gray-700">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
            Fund Request Type <span className="text-red-500">*</span>
          </label>
          {usedBeneficiaries.size > 0 && fundRequestType === 'Aid' && (
            <div className="mb-3 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
              <p className="text-xs text-blue-700 dark:text-blue-300">
                <strong>Note:</strong> {usedBeneficiaries.size} beneficiary{usedBeneficiaries.size > 1 ? 'ies have' : ' has'} already been used in other fund requests and will not appear in the dropdown.
              </p>
            </div>
          )}
          <div className="flex gap-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="fundRequestType"
                value="Aid"
                checked={fundRequestType === 'Aid'}
                onChange={() => {
                  setFundRequestType('Aid');
                  setFormData(prev => ({ ...prev, fund_request_type: 'Aid' }));
                }}
                className="w-4 h-4 text-blue-600"
                disabled={!!id}
              />
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Aid</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="fundRequestType"
                value="Article"
                checked={fundRequestType === 'Article'}
                onChange={() => {
                  setFundRequestType('Article');
                  setFormData(prev => ({ ...prev, fund_request_type: 'Article' }));
                }}
                className="w-4 h-4 text-blue-600"
                disabled={!!id}
              />
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Article</span>
            </label>
          </div>
        </div>

        {/* Aid Form */}
        {fundRequestType === 'Aid' && (
          <div className="space-y-6">
            {/* Aid Type Dropdown */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Aid Type <span className="text-red-500">*</span>
              </label>
              <select
                value={formData.aid_type || ''}
                onChange={(e) => {
                  setFormData(prev => ({ ...prev, aid_type: e.target.value || undefined }));
                }}
                className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                disabled={loadingAidArticles}
              >
                <option value="">Select Aid Type</option>
                {aidArticles.map((article) => (
                  <option key={article.id} value={article.article_name}>
                    {article.article_name}
                  </option>
                ))}
              </select>
              {loadingAidArticles && (
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  Loading aid types...
                </p>
              )}
              {!loadingAidArticles && aidArticles.length === 0 && (
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  No Aid articles found. Please add Aid articles in Article Management first.
                </p>
              )}
            </div>

            <div>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                    Recipients <span className="text-red-500">*</span>
                  </label>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    {recipients.length === 0 
                      ? 'Add at least one recipient to continue' 
                      : `${recipients.length} recipient${recipients.length > 1 ? 's' : ''} added`}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    handleAddRecipient();
                  }}
                  className="flex items-center gap-2 px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors shadow-sm"
                >
                  <Plus className="w-4 h-4" />
                  Add Recipient
                </button>
              </div>
              {errors.recipients && (
                <p className="mb-3 text-sm text-red-500">{errors.recipients}</p>
              )}
              <div className="space-y-6">
                {recipients.map((recipient, index) => (
                  <div key={index} className={`p-5 border-2 rounded-lg transition-colors ${
                    index % 2 === 0 
                      ? 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50' 
                      : 'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800'
                  }`}>
                    <div className="flex items-center justify-between mb-4 pb-3 border-b border-gray-200 dark:border-gray-700">
                      <div className="flex items-center gap-2">
                        <span className="text-base font-semibold text-gray-900 dark:text-white">
                          Recipient {index + 1}
                        </span>
                        {recipients.length > 1 && (
                          <span className="text-xs text-gray-500 dark:text-gray-400">
                            (of {recipients.length})
                          </span>
                        )}
                      </div>
                      {recipients.length > 1 && (
                        <button
                          type="button"
                          onClick={() => handleRemoveRecipient(index)}
                          className="p-1.5 text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20 rounded transition-colors"
                          title="Remove recipient"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {/* Beneficiary Type with District Dropdown inline */}
                      <div>
                        <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                          Beneficiary Type <span className="text-red-500">*</span>
                        </label>
                        <div className="flex gap-2">
                          <select
                            value={recipient.beneficiaryType || ''}
                            onChange={(e) => handleBeneficiaryTypeChange(index, e.target.value as any || undefined)}
                            className={`flex-1 px-3 py-2 text-sm border rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white ${
                              errors[`beneficiary_type_${index}`] ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'
                            }`}
                          >
                            <option value="">Select Type</option>
                            <option value="District">District</option>
                            <option value="Public">Public</option>
                            <option value="Institutions">Institutions</option>
                            <option value="Others">Others</option>
                          </select>
                          {/* District Dropdown - Only shown when beneficiary type is District */}
                          {recipient.beneficiaryType === 'District' && (
                            <select
                              value={recipient.selectedDistrictId || ''}
                              onChange={(e) => {
                                const districtIdValue = e.target.value || undefined;
                                const selectedDistrict = districts.find(d => d.id === districtIdValue);
                                const updated = [...recipients];
                                updated[index] = {
                                  ...updated[index],
                                  selectedDistrictId: districtIdValue,
                                  district_name: selectedDistrict?.name || undefined,
                                  beneficiary: '', // Clear beneficiary when district changes
                                  beneficiaryOptions: undefined, // Clear options to force reload
                                  loadingBeneficiaries: true, // Show loading state
                                };
                                setRecipients(updated);
                                // Reload beneficiaries with new district filter, passing districtId directly
                                // Use setTimeout to ensure state is updated before calling loadBeneficiaries
                                setTimeout(() => {
                                  loadBeneficiaries('District', index, districtIdValue);
                                }, 0);
                              }}
                              className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                              disabled={loadingDistricts}
                              title="Filter by District"
                            >
                              <option value="">All Districts</option>
                              {districts.map((district) => (
                                <option key={district.id} value={district.id}>
                                  {district.name}
                                </option>
                              ))}
                            </select>
                          )}
                        </div>
                        {errors[`beneficiary_type_${index}`] && (
                          <p className="mt-1 text-xs text-red-500">{errors[`beneficiary_type_${index}`]}</p>
                        )}
                      </div>

                      {/* Beneficiary Selection Dropdown - Always visible */}
                      <div>
                        <div className="flex items-center justify-between mb-1.5">
                          <label className="block text-xs font-medium text-gray-700 dark:text-gray-300">
                            Beneficiary
                          </label>
                          {recipient.beneficiary && (
                            <span className="text-xs text-green-600 dark:text-green-400 flex items-center gap-1">
                              <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                              Selected
                            </span>
                          )}
                        </div>
                        {recipient.loadingBeneficiaries ? (
                          <div className="flex items-center gap-2 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700">
                            <Loader2 className="w-4 h-4 animate-spin text-blue-600" />
                            <span className="text-sm text-gray-500 dark:text-gray-400">Loading beneficiaries...</span>
                          </div>
                        ) : (
                          <select
                            value={recipient.beneficiary || ''}
                            onChange={(e) => handleRecipientChange(index, 'beneficiary', e.target.value)}
                            className={`w-full px-3 py-2 text-sm border rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white ${
                              errors[`beneficiary_${index}`] ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'
                            }`}
                            disabled={recipient.loadingBeneficiaries || !recipient.beneficiaryType}
                          >
                            <option value="">
                              {recipient.beneficiaryType ? 'Select Beneficiary' : 'Select Beneficiary Type first'}
                            </option>
                            {recipient.beneficiaryOptions && recipient.beneficiaryOptions.length > 0 ? (
                              recipient.beneficiaryOptions.map((option, optIndex) => (
                                <option key={`${option.application_number}-${optIndex}`} value={option.display_text}>
                                  {option.display_text}
                                </option>
                              ))
                            ) : recipient.beneficiaryType ? (
                              <option value="" disabled>
                                {usedBeneficiaries.size > 0 || selectedBeneficiaries.size > 0
                                  ? 'No available beneficiaries (all are already used)'
                                  : 'No beneficiaries found'}
                              </option>
                            ) : null}
                          </select>
                        )}
                        {errors[`beneficiary_${index}`] && (
                          <p className="mt-1 text-xs text-red-500">{errors[`beneficiary_${index}`]}</p>
                        )}
                      </div>

                      {/* Name of Beneficiary */}
                      <div>
                        <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                          Name of Beneficiary <span className="text-red-500">*</span>
                        </label>
                        <input
                          type="text"
                          value={recipient.name_of_beneficiary || recipient.recipient_name || ''}
                          onChange={(e) => {
                            handleRecipientChange(index, 'name_of_beneficiary', e.target.value);
                            handleRecipientChange(index, 'recipient_name', e.target.value);
                          }}
                          className={`w-full px-3 py-2 text-sm border rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white ${
                            errors[`name_of_beneficiary_${index}`] ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'
                          }`}
                        />
                        {errors[`name_of_beneficiary_${index}`] && (
                          <p className="mt-1 text-xs text-red-500">{errors[`name_of_beneficiary_${index}`]}</p>
                        )}
                      </div>

                      {/* Name of Institution */}
                      <div>
                        <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                          Name of Institution <span className="text-red-500">*</span>
                        </label>
                        <input
                          type="text"
                          value={recipient.name_of_institution || ''}
                          onChange={(e) => handleRecipientChange(index, 'name_of_institution', e.target.value)}
                          className={`w-full px-3 py-2 text-sm border rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white ${
                            errors[`name_of_institution_${index}`] ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'
                          }`}
                        />
                        {errors[`name_of_institution_${index}`] && (
                          <p className="mt-1 text-xs text-red-500">{errors[`name_of_institution_${index}`]}</p>
                        )}
                      </div>

                      {/* Fund Requested and Aadhaar No in same row */}
                      <div>
                        <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                          Fund Requested <span className="text-red-500">*</span>
                        </label>
                        <input
                          type="number"
                          value={recipient.fund_requested || ''}
                          onChange={(e) => handleRecipientChange(index, 'fund_requested', parseFloat(e.target.value) || 0)}
                          min="0"
                          step="0.01"
                          className={`w-full px-3 py-2 text-sm border rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white ${
                            errors[`fund_requested_${index}`] ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'
                          }`}
                        />
                        {errors[`fund_requested_${index}`] && (
                          <p className="mt-1 text-xs text-red-500">{errors[`fund_requested_${index}`]}</p>
                        )}
                      </div>

                      {/* Aadhaar No - moved to right of Fund Requested */}
                      <div>
                        <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                          Aadhaar No <span className="text-red-500">*</span>
                        </label>
                        <input
                          type="text"
                          value={recipient.aadhar_number || ''}
                          onChange={(e) => {
                            // Only allow digits and limit to 12 characters
                            const value = e.target.value.replace(/\D/g, '').slice(0, 12);
                            handleRecipientChange(index, 'aadhar_number', value);
                          }}
                          maxLength={12}
                          className={`w-full px-3 py-2 text-sm border rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white ${
                            errors[`aadhar_number_${index}`] ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'
                          }`}
                          placeholder="Enter 12-digit Aadhaar number"
                        />
                        {errors[`aadhar_number_${index}`] && (
                          <p className="mt-1 text-xs text-red-500">{errors[`aadhar_number_${index}`]}</p>
                        )}
                      </div>

                      {/* Notes - Mandatory for Aid */}
                      <div className="md:col-span-2">
                        <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                          Details <span className="text-red-500">*</span>
                        </label>
                        <textarea
                          value={recipient.notes || ''}
                          onChange={(e) => handleRecipientChange(index, 'notes', e.target.value)}
                          rows={2}
                          className={`w-full px-3 py-2 text-sm border rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white ${
                            errors[`notes_${index}`] ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'
                          }`}
                          placeholder="Enter details"
                        />
                        {errors[`notes_${index}`] && (
                          <p className="mt-1 text-xs text-red-500">{errors[`notes_${index}`]}</p>
                        )}
                      </div>

                      {/* Cheque/RTGS in Favour - moved to end, full width */}
                      <div className="md:col-span-2">
                        <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                          Cheque/RTGS in Favour
                        </label>
                        <input
                          type="text"
                          value={recipient.cheque_in_favour || ''}
                          onChange={(e) => handleRecipientChange(index, 'cheque_in_favour', e.target.value)}
                          className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                        />
                      </div>
                    </div>

                    {/* Add Recipient Button After Each Block */}
                    <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700 flex justify-center">
                      <button
                        type="button"
                        onClick={() => handleAddRecipient(index)}
                        className="flex items-center gap-2 px-4 py-2 text-sm border border-blue-300 dark:border-blue-600 text-blue-600 dark:text-blue-400 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
                        title="Add another recipient after this one"
                      >
                        <Plus className="w-4 h-4" />
                        Add Recipient
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Article Form */}
        {fundRequestType === 'Article' && (
          <div className="space-y-6">
            {/* Supplier Information Section */}
            <div className="space-y-4">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Supplier Information</h3>
              
              {/* Supplier Name */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Supplier Name <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={supplierName}
                  onChange={(e) => setSupplierName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  placeholder="Enter supplier name"
                />
                {errors.supplier_name && (
                  <p className="mt-1 text-sm text-red-500">{errors.supplier_name}</p>
                )}
              </div>

              {/* GST NUMBER */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  GST Number <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={gstNumber}
                  onChange={(e) => setGstNumber(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  placeholder="Enter GST number"
                />
                {errors.gst_number && (
                  <p className="mt-1 text-sm text-red-500">{errors.gst_number}</p>
                )}
              </div>

              {/* Supplier Address */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Address <span className="text-red-500">*</span>
                </label>
                <textarea
                  value={supplierAddress}
                  onChange={(e) => setSupplierAddress(e.target.value)}
                  rows={2}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  placeholder="Enter supplier address"
                />
                {errors.supplier_address && (
                  <p className="mt-1 text-sm text-red-500">{errors.supplier_address}</p>
                )}
              </div>

              {/* City, State, Pincode in a row */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    City <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={supplierCity}
                    onChange={(e) => setSupplierCity(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    placeholder="Enter city"
                  />
                  {errors.supplier_city && (
                    <p className="mt-1 text-sm text-red-500">{errors.supplier_city}</p>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    State <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={supplierState}
                    onChange={(e) => setSupplierState(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    placeholder="Enter state"
                  />
                  {errors.supplier_state && (
                    <p className="mt-1 text-sm text-red-500">{errors.supplier_state}</p>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Pincode <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={supplierPincode}
                    onChange={(e) => setSupplierPincode(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    placeholder="Enter pincode"
                  />
                  {errors.supplier_pincode && (
                    <p className="mt-1 text-sm text-red-500">{errors.supplier_pincode}</p>
                  )}
                </div>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Articles <span className="text-red-500">*</span>
              </label>
              {errors.articles && (
                <p className="mb-2 text-sm text-red-500">{errors.articles}</p>
              )}
              <MultiSelectArticles
                articles={articles.map(a => ({
                  id: a.id,
                  name: a.article_name,
                  costPerUnit: a.cost_per_unit,
                  itemType: a.item_type || 'Article',
                  category: a.category,
                }))}
                selectedArticles={selectedArticles}
                onArticlesChange={handleArticlesChange}
                required
                showArticleFRFields={true}
                defaultCostToZero={true}
              />
              
              {selectedArticles.length > 0 && (
                <div className="mt-4 space-y-3">
                  {/* Grand Total */}
                  <div className="p-4 bg-gray-50 dark:bg-gray-700 rounded-lg">
                    <div className="flex justify-between items-center">
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">GRAND TOTAL:</span>
                      <span className="text-lg font-bold text-gray-900 dark:text-white">
                        {CURRENCY_SYMBOL} {formData.total_amount?.toLocaleString() || '0'}
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Comments - Only for Article type */}
            <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Comments
              </label>
              <textarea
                value={formData.notes || ''}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                rows={3}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                placeholder="Enter comments"
              />
            </div>
          </div>
        )}

        {/* Action Buttons */}
        <div className="mt-6 flex justify-end gap-3 pt-6 border-t border-gray-200 dark:border-gray-700">
          <button
            type="button"
            onClick={() => navigate('/fund-request')}
            className="px-6 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                Save
              </>
            )}
          </button>
        </div>
      </div>

      {/* Draft Restoration Notification */}
      {draftNotification.isOpen && (
        <div className="fixed top-4 right-4 z-50 animate-slide-in">
          <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg shadow-lg p-4 min-w-[350px] max-w-[450px]">
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0">
                <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400" />
              </div>
              <div className="flex-1">
                <p className="text-sm font-medium text-green-700 dark:text-green-300">
                  Draft successfully restored from {draftNotification.timestamp}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleClearDraft}
                  className="px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 hover:text-gray-900 dark:hover:text-gray-100 rounded transition-all duration-200 whitespace-nowrap transform hover:scale-105 active:scale-95"
                >
                  Clear Draft
                </button>
                <button
                  onClick={handleCloseDraftNotification}
                  className="flex-shrink-0 text-green-400 hover:text-green-600 dark:hover:text-green-300 transition-colors"
                  aria-label="Close notification"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default FundRequestForm;
