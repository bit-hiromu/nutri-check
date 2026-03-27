// 栄養成分データの型定義

/** 1メニューの栄養成分 */
export type MenuItem = {
  id: string;          // 一意ID（例: "mcdonalds_big_mac"）
  chain: string;       // チェーン名（例: "マクドナルド"）
  category: string;    // カテゴリ（例: "バーガー"）
  name: string;        // メニュー名
  calories: number;    // カロリー（kcal）
  protein: number;     // タンパク質（g）
  fat: number;         // 脂質（g）
  carbs: number;       // 炭水化物（g）
  salt?: number;       // 食塩相当量（g）、任意
  sourceUrl?: string;  // データ出典URL、任意
};

/** チェーン店の情報 */
export type Chain = {
  id: string;    // チェーンID（例: "mcdonalds"）
  name: string;  // チェーン名（例: "マクドナルド"）
  logo?: string; // ロゴ画像パス、任意
};

/** 合計栄養成分（複数メニュー選択時） */
export type NutritionTotal = {
  calories: number;
  protein: number;
  fat: number;
  carbs: number;
  salt: number;
};
