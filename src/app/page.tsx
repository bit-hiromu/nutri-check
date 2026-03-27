/**
 * ホームページ（Server Component）
 *
 * Server Component とは:
 *   Next.js App Router において、ファイルのトップレベルに "use client" を
 *   書かない場合、そのコンポーネントはサーバー側で実行される。
 *   fs（ファイルシステム）モジュールが使えるのはサーバー側だけなので、
 *   ここで JSON データを読み込んで Client Component に渡す。
 */

import { readFileSync, readdirSync } from "fs";
import { join } from "path";
import type { MenuItem } from "@/types/nutrition";
import NutriSearch from "@/components/NutriSearch";

/**
 * data/ ディレクトリ内の全 JSON ファイルを読み込んで、
 * すべてのメニューを1つの配列にまとめて返す。
 *
 * process.cwd() はプロジェクトルートのパスを返す。
 */
function loadAllItems(): MenuItem[] {
  const dataDir = join(process.cwd(), "data");
  // .json 拡張子のファイルだけを対象にする
  const files = readdirSync(dataDir).filter((f) => f.endsWith(".json"));
  // flatMap: 各ファイルの配列を展開して1つの配列に結合する
  return files.flatMap((file) => {
    const content = readFileSync(join(dataDir, file), "utf-8");
    return JSON.parse(content) as MenuItem[];
  });
}

export default function Home() {
  // サーバー側で全データを読み込む
  const allItems = loadAllItems();

  // チェーン名一覧を重複なしで取得してソート
  // Set はユニークな値のコレクション。スプレッド構文 [...] で配列に変換する。
  const chains = [...new Set(allItems.map((i) => i.chain))].sort();

  return (
    <div className="min-h-screen bg-gray-50">
      {/* ヘッダー */}
      <header className="bg-green-600 text-white py-4 px-4 shadow-md">
        <div className="max-w-5xl mx-auto">
          <h1 className="text-xl font-bold tracking-tight">🍱 NutriCheck</h1>
          <p className="text-xs text-green-100 mt-0.5">
            外食チェーン栄養チェッカー — {allItems.length.toLocaleString()}件のメニューを収録
          </p>
        </div>
      </header>

      {/* メインコンテンツ */}
      <main className="max-w-5xl mx-auto px-4 py-6">
        {/*
          allItems と chains をサーバーから Client Component に渡す。
          Next.js が自動的にシリアライズ（JSON化）して送信する。
        */}
        <NutriSearch allItems={allItems} chains={chains} />
      </main>

      {/* フッター */}
      <footer className="mt-12 py-6 text-center text-xs text-gray-400">
        <p>栄養成分は各社公式PDFの値です。最新情報は各チェーン公式サイトをご確認ください。</p>
      </footer>
    </div>
  );
}
