# 🍱 NutriCheck — 外食チェーン栄養チェッカー

外食チェーン店の栄養成分（カロリー・タンパク質・脂質・炭水化物）を横断検索し、
複数メニューの合計栄養成分をリアルタイムで計算できるWebサービスです。

## 主な機能

- **横断検索** — 7チェーン・1,500件以上のメニューをまとめて検索
- **チェーン絞り込み** — 特定のチェーン店だけ表示
- **複数選択・合計計算** — メニューを複数選んで合計カロリー・栄養素を即時計算
- **自動データ更新** — GitHub Actions が毎朝0時（JST）に各チェーンの公式PDFから最新データを取得

## 対応チェーン（2026年3月現在）

| チェーン | メニュー数 | データ出典 |
|---------|-----------|-----------|
| CoCo壱番屋 | 約190件 | 公式栄養成分PDF |
| すき家 | 約450件 | 公式栄養成分PDF |
| なか卯 | 約270件 | 公式栄養成分PDF |
| モスバーガー | 約210件 | 公式栄養成分PDF |
| 松屋 | 約280件 | 公式栄養成分PDF |
| 天丼てんや | 約80件 | 公式栄養成分PDF |
| ケンタッキーフライドチキン | 約30件 | 公式栄養成分PDF |

---

## 技術スタック

| 役割 | 技術 |
|------|------|
| フレームワーク | [Next.js 16](https://nextjs.org/) (App Router) |
| 言語 | TypeScript |
| スタイリング | [Tailwind CSS v4](https://tailwindcss.com/) |
| 検索 | [Fuse.js](https://www.fusejs.io/)（クライアントサイド曖昧検索）|
| データ取得 | Python + pdfplumber |
| 自動更新 | GitHub Actions（毎日0:00 JST）|
| ホスティング | Vercel（予定）|

---

## ローカル環境構築

### 必要なもの

- **Node.js** v18以上（推奨: v20以上）
- **Python** 3.10以上
- **Git**

### 手順

#### 1. リポジトリのクローン

```bash
git clone https://github.com/あなたのユーザー名/nutri-check.git
cd nutri-check
```

#### 2. フロントエンドの依存ライブラリをインストール

```bash
npm install
```

#### 3. Pythonの依存ライブラリをインストール

栄養データ取得スクリプト（`scripts/fetch_nutrition.py`）に必要なライブラリです。

```bash
pip install -r scripts/requirements.txt
```

#### 4. 栄養データを取得する

各チェーンの公式PDFをダウンロードして `data/` フォルダにJSONを生成します。

```bash
python scripts/fetch_nutrition.py
```

完了すると `data/ichibanya.json`, `data/sukiya.json` などのファイルが作成されます。

> **注意**: PDFのダウンロードがあるため、数十秒〜1分程度かかります。

#### 5. 開発サーバーを起動する

```bash
npm run dev
```

ブラウザで [http://localhost:3000](http://localhost:3000) を開くと動作確認できます。

---

## 主なコマンド

```bash
# 開発サーバー起動（ファイル変更を自動反映）
npm run dev

# 本番ビルド
npm run build

# 本番サーバー起動（build後に実行）
npm start

# 栄養データを手動で更新
python scripts/fetch_nutrition.py
```

---

## プロジェクト構成

```
nutri-check/
├── src/
│   ├── app/
│   │   ├── layout.tsx        # ページ全体のレイアウト・メタデータ
│   │   ├── page.tsx          # ホームページ（Server Component、JSONデータ読み込み）
│   │   └── globals.css       # グローバルスタイル
│   ├── components/
│   │   └── NutriSearch.tsx   # 検索・選択・合計計算UI（Client Component）
│   ├── lib/
│   │   └── nutrition.ts      # 合計計算ユーティリティ関数
│   └── types/
│       └── nutrition.ts      # 型定義（MenuItem, NutritionTotal など）
├── data/
│   ├── ichibanya.json        # CoCo壱番屋の栄養データ（自動生成）
│   ├── sukiya.json           # すき家の栄養データ（自動生成）
│   └── ...                   # 各チェーンのJSONファイル
├── scripts/
│   ├── fetch_nutrition.py    # データ取得・変換スクリプト
│   ├── chains.json           # チェーン設定（URL・列名マッピング）
│   └── requirements.txt      # Python依存ライブラリ
└── .github/
    └── workflows/
        └── update-nutrition.yml  # 自動更新ワークフロー（GitHub Actions）
```

---

## データ更新の仕組み

GitHub Actions を使って毎日自動更新しています。

```
毎日 0:00 JST
    ↓
fetch_nutrition.py が chains.json の設定に従い
各チェーンの公式PDFをダウンロード・解析
    ↓
data/*.json を上書き更新
    ↓
変更があれば自動でコミット・プッシュ
```

新しいチェーンを追加したい場合は `scripts/chains.json` に設定を追加してください。

---

## 注意事項

- 栄養成分の数値は各社公式PDFの値です。最新情報は各チェーンの公式サイトをご確認ください。
- チェーンによってはPDFのURL変更により取得が失敗することがあります（その場合は前回データを維持します）。
