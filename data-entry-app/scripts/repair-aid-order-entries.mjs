import { createClient } from '@supabase/supabase-js';

const SUPABASE_URL = 'https://miftepyeoqfjyjeqffet.supabase.co';
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1pZnRlcHllb3FmanlqZXFmZmV0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjU3ODY5NzgsImV4cCI6MjA4MTM2Mjk3OH0.19nAsbnhQmTNrp6XqZ-iiUULMW8tnwSHIx5GbP5-cGY';

const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, { auth: { persistSession: false } });

const norm = (v) => String(v || '').trim().toLowerCase();
const isAidItemType = (itemType) => {
  const v = norm(itemType);
  return v === 'aid' || /\baid\b/.test(v);
};
const parseBeneficiary = (value) => {
  const text = String(value || '').trim();
  const parts = text.split(' - ').map((p) => p.trim()).filter(Boolean);
  return {
    appNo: parts[0] || '',
    aidLabel: parts[1] || '',
  };
};

const textMatches = (a, b) => {
  const x = norm(a);
  const y = norm(b);
  if (!x || !y) return false;
  return x === y || x.includes(y) || y.includes(x);
};

async function findAidArticleId(aidType, aidArticles) {
  const t = norm(aidType);
  if (!t) return null;

  let match = aidArticles.find((a) => norm(a.article_name) === t);
  if (match) return match.id;

  match = aidArticles.find((a) => norm(a.category) === t);
  if (match) return match.id;

  match = aidArticles.find((a) => norm(a.article_name).includes(t));
  if (match) return match.id;

  match = aidArticles.find((a) => norm(a.category).includes(t));
  if (match) return match.id;

  match = aidArticles.find((a) => t.includes(norm(a.article_name)));
  if (match) return match.id;

  return null;
}

async function resolveFromMaster(recipient, aidHint) {
  const { appNo, aidLabel } = parseBeneficiary(recipient.beneficiary);
  if (!appNo) return null;

  const hint = String(aidHint || aidLabel || '').trim();
  const type = String(recipient.beneficiary_type || '').trim();

  const pickAidRow = (rows) => {
    const filtered = (rows || []).map((row) => {
      const article = Array.isArray(row.articles) ? row.articles[0] : row.articles;
      return {
        articleId: row.article_id,
        itemType: article?.item_type,
        articleName: article?.article_name,
        category: article?.category,
      };
    }).filter((row) => isAidItemType(row.itemType));

    if (!filtered.length) return null;
    if (hint) {
      const matched = filtered.find((row) => textMatches(row.articleName, hint) || textMatches(row.category, hint));
      if (matched) return matched.articleId;
    }
    return filtered[0].articleId;
  };

  if (type === 'District') {
    const { data, error } = await supabase
      .from('district_beneficiary_entries')
      .select('article_id, articles:article_id(item_type, article_name, category)')
      .eq('application_number', appNo)
      .order('created_at', { ascending: false });
    if (error) throw error;
    return pickAidRow(data);
  }

  if (type === 'Public') {
    const { data, error } = await supabase
      .from('public_beneficiary_entries')
      .select('article_id, articles:article_id(item_type, article_name, category)')
      .eq('application_number', appNo)
      .order('created_at', { ascending: false });
    if (error) throw error;
    return pickAidRow(data);
  }

  if (type === 'Institutions' || type === 'Others') {
    const { data, error } = await supabase
      .from('institutions_beneficiary_entries')
      .select('article_id, articles:article_id(item_type, article_name, category)')
      .eq('application_number', appNo)
      .order('created_at', { ascending: false });
    if (error) throw error;
    return pickAidRow(data);
  }

  return null;
}

async function main() {
  const dryRun = process.argv.includes('--dry-run');

  const [{ data: allArticles, error: aErr }, { data: aidFundRequests, error: frErr }] = await Promise.all([
    supabase.from('articles').select('id, article_name, category, item_type'),
    supabase.from('fund_request').select('id, fund_request_number, aid_type').eq('fund_request_type', 'Aid'),
  ]);
  if (aErr) throw aErr;
  if (frErr) throw frErr;

  const aidArticles = (allArticles || []).filter((a) => isAidItemType(a.item_type));
  const frById = new Map((aidFundRequests || []).map((fr) => [fr.id, fr]));
  const aidFrIds = Array.from(frById.keys());

  const { data: recipients, error: rErr } = await supabase
    .from('fund_request_recipients')
    .select('id, fund_request_id, beneficiary_type, beneficiary, recipient_name, name_of_beneficiary, fund_requested')
    .in('fund_request_id', aidFrIds)
    .order('created_at', { ascending: true });
  if (rErr) throw rErr;

  const repairRows = [];
  const unresolved = [];

  for (const recipient of recipients || []) {
    const fr = frById.get(recipient.fund_request_id);
    const aidHint = String(fr?.aid_type || '').trim() || parseBeneficiary(recipient.beneficiary).aidLabel;

    let articleId = await findAidArticleId(aidHint, aidArticles);
    if (!articleId) {
      articleId = await resolveFromMaster(recipient, aidHint);
    }

    if (!articleId) {
      unresolved.push({
        fund_request_number: fr?.fund_request_number || recipient.fund_request_id,
        recipient_name: recipient.recipient_name || recipient.name_of_beneficiary || null,
        beneficiary_type: recipient.beneficiary_type || null,
        beneficiary: recipient.beneficiary || null,
      });
      continue;
    }

    repairRows.push({
      article_id: articleId,
      quantity_ordered: 1,
      order_date: new Date().toISOString().split('T')[0],
      status: 'pending',
      supplier_name: null,
      supplier_contact: null,
      unit_price: Number(recipient.fund_requested || 0),
      total_amount: Number(recipient.fund_requested || 0),
      notes: `Rebuilt from Aid Fund Request: ${fr?.fund_request_number || recipient.fund_request_id} - ${recipient.recipient_name || recipient.name_of_beneficiary || 'Recipient'}`,
      fund_request_id: recipient.fund_request_id,
    });
  }

  console.log(JSON.stringify({
    mode: dryRun ? 'dry-run' : 'apply',
    aidFundRequests: aidFrIds.length,
    recipients: (recipients || []).length,
    willCreateOrderRows: repairRows.length,
    unresolvedRecipients: unresolved.length,
    unresolvedPreview: unresolved.slice(0, 10),
  }, null, 2));

  if (dryRun) return;

  // Delete current Aid FR order rows
  const { error: delErr } = await supabase
    .from('order_entries')
    .delete()
    .in('fund_request_id', aidFrIds);
  if (delErr) throw delErr;

  // Insert rebuilt rows in chunks
  const CHUNK = 500;
  for (let i = 0; i < repairRows.length; i += CHUNK) {
    const chunk = repairRows.slice(i, i + CHUNK);
    const { error: insErr } = await supabase.from('order_entries').insert(chunk);
    if (insErr) throw insErr;
  }

  // Print quick Education Aid check
  const eduArticle = aidArticles.find((a) => norm(a.article_name) === 'education aid');
  if (eduArticle) {
    const [{ data: d }, { data: p }, { data: i }, { data: o }] = await Promise.all([
      supabase.from('district_beneficiary_entries').select('quantity').eq('article_id', eduArticle.id),
      supabase.from('public_beneficiary_entries').select('quantity').eq('article_id', eduArticle.id),
      supabase.from('institutions_beneficiary_entries').select('quantity').eq('article_id', eduArticle.id),
      supabase.from('order_entries').select('quantity_ordered,status').eq('article_id', eduArticle.id),
    ]);

    const needed = (d.data || []).reduce((s, r) => s + (r.quantity || 0), 0)
      + (p.data || []).reduce((s, r) => s + (r.quantity || 0), 0)
      + (i.data || []).reduce((s, r) => s + (r.quantity || 0), 0);
    const ordered = (o.data || []).filter((r) => r.status !== 'cancelled').reduce((s, r) => s + (r.quantity_ordered || 0), 0);

    console.log(JSON.stringify({ educationAid: { needed, ordered, pending: needed - ordered } }, null, 2));
  }
}

main().catch((err) => {
  console.error('repair-aid-order-entries failed:', err);
  process.exit(1);
});
