import React from 'react';
import { X, Plus, Minus } from 'lucide-react';
import type { ArticleSelection } from '../data/mockData';
import { CURRENCY_SYMBOL } from '../constants/currency';
interface ArticleRowProps {
  article: ArticleSelection;
  onUpdate: (updatedArticle: ArticleSelection) => void;
  onRemove: () => void;
  showRemove?: boolean;
  originalCostPerUnit?: number; // Original cost from the article catalog
  showArticleFRFields?: boolean; // If true, show cheque_in_favour and supplier_article_name instead of comments
}

const ArticleRow: React.FC<ArticleRowProps> = ({
  article,
  onUpdate,
  onRemove,
  showRemove = true,
  originalCostPerUnit,
  showArticleFRFields = false,
}) => {
  // Cost is editable only if original cost is 0
  // Handle both number and string comparisons, and fallback to current value if original not provided
  const originalCost = originalCostPerUnit !== undefined ? Number(originalCostPerUnit) : Number(article.costPerUnit);
  const isCostEditable = originalCost === 0;
  const handleQuantityChange = (delta: number) => {
    const newQuantity = Math.max(1, article.quantity + delta);
    const newTotalValue = newQuantity * article.costPerUnit;
    onUpdate({
      ...article,
      quantity: newQuantity,
      totalValue: newTotalValue,
    });
  };

  const handleQuantityInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = parseInt(e.target.value, 10);
    if (!isNaN(value) && value > 0) {
      const newTotalValue = value * article.costPerUnit;
      onUpdate({
        ...article,
        quantity: value,
        totalValue: newTotalValue,
      });
    }
  };

  const handleCostPerUnitChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const inputValue = e.target.value;
    // Allow empty string for clearing the value
    if (inputValue === '') {
      onUpdate({
        ...article,
        costPerUnit: 0,
        totalValue: 0,
      });
      return;
    }
    const value = parseFloat(inputValue) || 0;
    const newTotalValue = value * article.quantity;
    onUpdate({
      ...article,
      costPerUnit: value,
      totalValue: newTotalValue,
    });
  };

  const handleCommentsChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onUpdate({
      ...article,
      comments: e.target.value,
    });
  };

  const handleChequeInFavourChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onUpdate({
      ...article,
      cheque_in_favour: e.target.value,
    });
  };

  const handleSupplierArticleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onUpdate({
      ...article,
      supplier_article_name: e.target.value,
    });
  };

  const handleDescriptionChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onUpdate({
      ...article,
      description: e.target.value,
    });
  };

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 bg-white dark:bg-gray-800">
      {/* First Line */}
      <div className="flex items-center gap-3 md:gap-6 flex-wrap">
        {/* Article Name */}
        <div className="flex-1 min-w-[150px]">
          <h4 className="font-medium text-gray-900 dark:text-white text-sm truncate">
            {article.articleName}
          </h4>
        </div>

        {/* Quantity */}
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-gray-700 dark:text-gray-300 whitespace-nowrap hidden sm:inline">
            Qty:
          </label>
          <button
            type="button"
            onClick={() => handleQuantityChange(-1)}
            className="p-1 rounded border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            aria-label="Decrease quantity"
          >
            <Minus className="w-3 h-3" />
          </button>
          <input
            type="number"
            min="1"
            value={article.quantity}
            onChange={handleQuantityInput}
            className="w-14 md:w-16 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-center text-sm"
          />
          <button
            type="button"
            onClick={() => handleQuantityChange(1)}
            className="p-1 rounded border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            aria-label="Increase quantity"
          >
            <Plus className="w-3 h-3" />
          </button>
        </div>

        {/* Cost Per Unit - Editable only if original cost is 0 */}
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-gray-700 dark:text-gray-300 whitespace-nowrap hidden sm:inline">
            Cost:
          </label>
          {isCostEditable ? (
            <input
              type="number"
              min="0"
              step="1"
              value={article.costPerUnit === 0 ? '' : article.costPerUnit}
              onChange={handleCostPerUnitChange}
              className="w-20 md:w-24 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
              placeholder="0"
            />
          ) : (
            <div className="w-20 md:w-24 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white text-xs md:text-sm text-right">
              {CURRENCY_SYMBOL}{article.costPerUnit.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          )}
        </div>

        {/* Total Value */}
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-gray-700 dark:text-gray-300 whitespace-nowrap hidden sm:inline">
            Total:
          </label>
          <div className="w-24 md:w-28 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white font-medium text-xs md:text-sm text-right">
            {CURRENCY_SYMBOL}{article.totalValue.toLocaleString('en-IN')}
          </div>
        </div>

        {/* Comments (for non-Article FR contexts) */}
        {!showArticleFRFields && (
          <div className="flex items-center gap-1 flex-1 min-w-[150px]">
            <label className="text-xs font-medium text-gray-700 dark:text-gray-300 whitespace-nowrap hidden md:inline">
              Comments:
            </label>
            <input
              type="text"
              value={article.comments || ''}
              onChange={handleCommentsChange}
              className="flex-1 min-w-0 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
              placeholder="Comments"
            />
          </div>
        )}

        {/* Remove Button */}
        {showRemove && (
          <button
            onClick={onRemove}
            className="p-1 rounded hover:bg-red-100 dark:hover:bg-red-900/30 text-red-600 dark:text-red-400 transition-colors flex-shrink-0"
            aria-label="Remove article"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Second Line - Supplier Article Name and Description (for Article FR) */}
      {showArticleFRFields && (
        <div className="flex flex-col gap-2 mt-2">
          <div className="flex items-center gap-2 md:gap-4 flex-wrap">
            <div className="flex items-center gap-1 flex-1 min-w-[150px]">
              <label className="text-xs font-medium text-gray-700 dark:text-gray-300 whitespace-nowrap hidden md:inline">
                Supplier Article Name:
              </label>
              <input
                type="text"
                value={article.supplier_article_name || ''}
                onChange={handleSupplierArticleNameChange}
                className="flex-1 min-w-0 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                placeholder="Supplier Article Name"
              />
            </div>

            <div className="flex items-center gap-1 flex-1 min-w-[150px]">
              <label className="text-xs font-medium text-gray-700 dark:text-gray-300 whitespace-nowrap hidden md:inline">
                Description:
              </label>
              <input
                type="text"
                value={article.description || ''}
                onChange={handleDescriptionChange}
                className="flex-1 min-w-0 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                placeholder="Description"
              />
            </div>
          </div>
          
          <div className="flex items-center gap-1 flex-1 min-w-[120px]">
            <label className="text-xs font-medium text-gray-700 dark:text-gray-300 whitespace-nowrap hidden md:inline">
              Cheque/RTGS in Favour:
            </label>
            <input
              type="text"
              value={article.cheque_in_favour || ''}
              onChange={handleChequeInFavourChange}
              className="flex-1 min-w-0 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
              placeholder="Cheque/RTGS in Favour"
            />
          </div>
        </div>
      )}
    </div>
  );
};

export default ArticleRow;
