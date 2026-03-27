// 栄養データの読み込み・操作ユーティリティ
import type { MenuItem, NutritionTotal } from "@/types/nutrition";

/**
 * 選択済みメニューの栄養成分合計を計算する
 */
export function calcTotal(items: MenuItem[]): NutritionTotal {
  return items.reduce(
    (acc, item) => ({
      calories: acc.calories + item.calories,
      protein: acc.protein + item.protein,
      fat: acc.fat + item.fat,
      carbs: acc.carbs + item.carbs,
      salt: acc.salt + (item.salt ?? 0),
    }),
    { calories: 0, protein: 0, fat: 0, carbs: 0, salt: 0 }
  );
}
