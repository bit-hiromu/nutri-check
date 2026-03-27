"use client";

/**
 * NutriSearch — 検索・選択・合計計算の Client Component
 *
 * "use client" とは:
 *   このコンポーネントはブラウザ（クライアント）側で動く。
 *   useState や useEffect などの React フックはクライアント側でしか使えない。
 *   検索入力や選択状態の管理にはこれらが必要なので、"use client" が必要になる。
 */

import { useState, useMemo } from "react";
import Fuse from "fuse.js";
import type { MenuItem, NutritionTotal } from "@/types/nutrition";
import { calcTotal } from "@/lib/nutrition";

/**
 * Fuse.js の検索オプション
 *
 * Fuse.js とは: JavaScript 製の「曖昧検索（ファジー検索）」ライブラリ。
 *   完全一致でなくても、入力に近いものを見つけてくれる。
 *   例: "ぎゅうどん" で "牛丼" を検索できる（ひらがな/漢字は別途対応が必要だが）。
 *
 * keys.weight: 数値が大きいほど検索の優先度が高い
 * threshold: 0=完全一致のみ、1=何でもマッチ。0.35 は適度な曖昧さ
 */
const FUSE_OPTIONS = {
  keys: [
    { name: "name", weight: 2 },       // メニュー名を最優先
    { name: "chain", weight: 1 },      // チェーン名
    { name: "category", weight: 0.5 }, // カテゴリ
  ],
  threshold: 0.35,
};

// このコンポーネントが受け取る props（引数）の型定義
type Props = {
  allItems: MenuItem[]; // 全チェーンの全メニュー
  chains: string[];     // チェーン名の一覧（フィルター用）
};

export default function NutriSearch({ allItems, chains }: Props) {
  /**
   * useState: コンポーネントの「状態（state）」を管理するフック。
   *   状態が変わると、React が自動的に画面を再描画する。
   *   useState(初期値) → [現在の値, 値を更新する関数] を返す。
   */
  const [query, setQuery] = useState("");           // 検索クエリ
  const [chainFilter, setChainFilter] = useState(""); // チェーンフィルター（""=すべて）
  const [selected, setSelected] = useState<MenuItem[]>([]); // 選択済みメニュー

  /**
   * useMemo: 計算結果をキャッシュするフック。
   *   第2引数の配列（依存配列）に含まれる値が変わったときだけ再計算する。
   *   毎回レンダリングするたびに重い計算が走るのを防ぐ。
   */

  // Fuse インスタンスの生成（allItems が変わったときだけ再生成）
  const fuse = useMemo(() => new Fuse(allItems, FUSE_OPTIONS), [allItems]);

  // 検索・フィルター結果の計算
  const results = useMemo(() => {
    let items: MenuItem[];

    if (query.trim()) {
      // Fuse.js で曖昧検索 → { item, score } の配列が返るので .item だけ取り出す
      items = fuse.search(query).map((r) => r.item);
    } else {
      // クエリが空の場合は全件を対象にする
      items = [...allItems];
    }

    // チェーンフィルターが選択されている場合は絞り込む
    if (chainFilter) {
      items = items.filter((i) => i.chain === chainFilter);
    }

    // 表示件数を50件に制限（大量描画によるパフォーマンス低下を防ぐ）
    return items.slice(0, 50);
  }, [query, chainFilter, fuse, allItems]);

  // 合計栄養成分の計算（選択済みアイテムが変わるたびに再計算）
  const total: NutritionTotal = useMemo(() => calcTotal(selected), [selected]);

  // ── イベントハンドラ ──────────────────────────────────

  /** メニューを選択リストに追加する（同じIDは追加しない） */
  const addItem = (item: MenuItem) => {
    if (selected.some((s) => s.id === item.id)) return;
    // prev は直前の状態。スプレッド構文で既存の配列に item を追加した新しい配列を作る
    setSelected((prev) => [...prev, item]);
  };

  /** メニューを選択リストから削除する */
  const removeItem = (id: string) => {
    // filter: 条件に一致するものだけ残す（一致しないものを除外）
    setSelected((prev) => prev.filter((s) => s.id !== id));
  };

  /** 選択をすべてクリアする */
  const clearAll = () => setSelected([]);

  /** 指定 ID のアイテムが選択済みかどうか */
  const isSelected = (id: string) => selected.some((s) => s.id === id);

  // ── 描画（JSX） ──────────────────────────────────────

  return (
    <div className="flex flex-col gap-5">

      {/* ── 検索バー・フィルター ── */}
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="メニューを検索（例: 牛丼、チキン、サラダ）"
          className="flex-1 rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm shadow-sm
                     focus:border-green-500 focus:outline-none focus:ring-2 focus:ring-green-200"
        />
        <select
          value={chainFilter}
          onChange={(e) => setChainFilter(e.target.value)}
          className="rounded-lg border border-gray-300 bg-white px-3 py-2.5 text-sm shadow-sm
                     focus:border-green-500 focus:outline-none focus:ring-2 focus:ring-green-200"
        >
          <option value="">全チェーン</option>
          {chains.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>

      {/* ── 2カラムレイアウト（大画面では左右並び） ── */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2 lg:items-start">

        {/* ── 左: 検索結果リスト ── */}
        <section className="flex flex-col gap-2">
          <p className="text-xs text-gray-500">
            {results.length}件表示
            {results.length === 50 && "（上位50件）— 検索で絞り込んでください"}
          </p>

          {/* スクロール可能なリスト（max-h で高さを制限） */}
          <div className="flex flex-col gap-2 max-h-[65vh] overflow-y-auto pr-1">
            {results.map((item) => (
              <div
                key={item.id}
                className="rounded-xl border border-gray-200 bg-white p-3 shadow-sm"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    {/* truncate: 長いテキストを省略記号（…）で切る */}
                    <p className="font-medium text-sm leading-snug">{item.name}</p>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {item.chain}
                      {item.category && item.category !== `${item.chain}メニュー`
                        ? ` · ${item.category}`
                        : ""}
                    </p>
                    {/* 栄養成分サマリー */}
                    <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs">
                      <span className="font-bold text-orange-500">{item.calories} kcal</span>
                      <span className="text-gray-500">P {item.protein}g</span>
                      <span className="text-gray-500">F {item.fat}g</span>
                      <span className="text-gray-500">C {item.carbs}g</span>
                      {item.salt != null && (
                        <span className="text-gray-400">塩 {item.salt}g</span>
                      )}
                    </div>
                  </div>

                  {/* 追加ボタン */}
                  <button
                    onClick={() => addItem(item)}
                    disabled={isSelected(item.id)}
                    aria-label={`${item.name}を追加`}
                    className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center
                                text-sm font-bold transition-colors
                                ${isSelected(item.id)
                                  ? "bg-green-100 text-green-500 cursor-default"
                                  : "bg-green-500 text-white hover:bg-green-600 active:scale-95"
                                }`}
                  >
                    {isSelected(item.id) ? "✓" : "+"}
                  </button>
                </div>
              </div>
            ))}

            {results.length === 0 && (
              <p className="text-center text-sm text-gray-400 py-8">
                該当するメニューが見つかりません
              </p>
            )}
          </div>
        </section>

        {/* ── 右: 選択リスト + 合計 ── */}
        <section className="flex flex-col gap-3">

          {/* 選択リストのヘッダー */}
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-sm text-gray-700">
              選択中 <span className="text-green-600">({selected.length}件)</span>
            </h2>
            {selected.length > 0 && (
              <button
                onClick={clearAll}
                className="text-xs text-red-400 hover:text-red-600 hover:underline"
              >
                すべて削除
              </button>
            )}
          </div>

          {/* 選択済みメニューの一覧 */}
          {selected.length === 0 ? (
            <div className="rounded-xl border border-dashed border-gray-300 bg-white py-8 text-center">
              <p className="text-sm text-gray-400">＋ボタンでメニューを追加</p>
            </div>
          ) : (
            <div className="flex flex-col gap-1.5 max-h-[30vh] overflow-y-auto pr-1">
              {selected.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between rounded-lg border border-green-100
                             bg-green-50 px-3 py-2 gap-2"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{item.name}</p>
                    <p className="text-xs text-gray-500">
                      {item.chain} · {item.calories} kcal
                    </p>
                  </div>
                  <button
                    onClick={() => removeItem(item.id)}
                    aria-label={`${item.name}を削除`}
                    className="shrink-0 w-6 h-6 flex items-center justify-center rounded-full
                               text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors text-base"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* ── 合計栄養成分パネル ── */}
          {selected.length > 0 && (
            <div className="rounded-2xl bg-green-600 text-white p-5 shadow-md">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-green-100 mb-3">
                合計栄養成分
              </h3>

              {/* カロリー（大きく表示） */}
              <p className="text-4xl font-bold leading-none">
                {total.calories.toFixed(0)}
                <span className="text-base font-normal text-green-100 ml-1">kcal</span>
              </p>

              {/* P / F / C グリッド */}
              <div className="mt-4 grid grid-cols-3 gap-2 text-center">
                {[
                  { label: "タンパク質", value: total.protein, unit: "g" },
                  { label: "脂質", value: total.fat, unit: "g" },
                  { label: "炭水化物", value: total.carbs, unit: "g" },
                ].map(({ label, value, unit }) => (
                  <div key={label} className="rounded-xl bg-white/20 py-2">
                    <p className="text-lg font-bold">
                      {value.toFixed(1)}
                      <span className="text-xs font-normal">{unit}</span>
                    </p>
                    <p className="text-xs text-green-100">{label}</p>
                  </div>
                ))}
              </div>

              {/* 食塩相当量（あれば表示） */}
              {total.salt > 0 && (
                <p className="mt-3 text-xs text-green-100">
                  食塩相当量: {total.salt.toFixed(1)} g
                </p>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
