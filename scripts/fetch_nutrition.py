"""
栄養成分データ自動取得スクリプト

chains.json に定義されたチェーン店の Excel または PDF をダウンロードし、
栄養データをパースして data/{chain_id}.json に出力する。

対応フォーマット:
  - Excel (.xlsx / .xls): pandas + openpyxl で解析（推奨）
  - PDF (.pdf): pdfplumber で解析

chains.json の主要オプション:
  file_url      : ダウンロード先URL（拡張子でフォーマットを自動判別）
  columns       : PDFの列名 → フィールド名 のマッピング
  category_col  : カテゴリを取得する列名（省略時はテーブルヘッダーを使用）
  size_col      : サイズ列名（省略時は無視。メニュー名に " サイズ名" を付加）
  sheet         : Excel のシート名またはインデックス（省略時=0）
  header_row    : ヘッダー行番号（省略時は自動検出）
  skip_rows     : 先頭スキップ行数（省略時=0）
"""

import json
import os
import re
import sys
import tempfile
import traceback
from pathlib import Path

import pandas as pd
import pdfplumber
import requests

# ── パス定義 ──────────────────────────────────────────
ROOT_DIR = Path(__file__).parent.parent   # プロジェクトルート
DATA_DIR = ROOT_DIR / "data"              # 出力先ディレクトリ
CHAINS_FILE = Path(__file__).parent / "chains.json"  # チェーン設定ファイル

# 対応拡張子の分類
EXCEL_EXTS = {".xlsx", ".xls"}
PDF_EXTS = {".pdf"}


# ── 共通ユーティリティ ─────────────────────────────────

def download_file(url: str, dest_path: str) -> None:
    """
    ファイルをURLからダウンロードして保存する。

    User-Agent を設定する理由:
      一部サーバーはボットからのアクセスをブロックするため、
      一般的なブラウザに見せかけるヘッダーを付与する。
    """
    headers = {"User-Agent": "Mozilla/5.0 (compatible; NutriCheckBot/1.0)"}
    # timeout=30: 30秒応答がなければ例外を発生させる（無限待ちを防ぐ）
    response = requests.get(url, headers=headers, timeout=30)
    # ステータスコードが 4xx/5xx の場合に例外を発生させる
    response.raise_for_status()
    with open(dest_path, "wb") as f:
        f.write(response.content)


def normalize_header(text) -> str:
    """
    ヘッダー文字列を正規化して列名の表記ゆれを吸収する。

    処理内容:
      1. 括弧内の単位表記を除去  例: "エネルギー(kcal)" → "エネルギー"
      2. 空白・改行・全角スペースを除去
    """
    # pandas の NaN（欠損値）は空文字として扱う
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    text = str(text)
    # 正規表現で括弧（半角・全角）とその内容を削除
    text = re.sub(r"[（(][^）)]*[）)]", "", text)
    return text.strip().replace("\n", "").replace(" ", "").replace("　", "")


def parse_float(value) -> float | None:
    """
    セルの値を float（小数）に変換する。

    変換できない場合（文字列や欠損値）は None を返す。
    「－」などのハイフン類は欠損値表記として 0.0 に変換する。
    """
    if value is None:
        return None
    # pandas の数値型はそのまま変換できる
    if isinstance(value, (int, float)):
        return float(value) if not pd.isna(value) else None
    text = str(value).strip()
    # ハイフン類（欠損値の表記）→ 0 に統一
    text = re.sub(r"^[－\-−‐‑]$", "0", text)
    # カンマ区切り数値（例: "1,116"）のカンマを除去
    text = text.replace(",", "")
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def build_col_map_from_headers(headers: list, col_config: dict) -> dict[str, int]:
    """
    ヘッダー行のリストと設定から {フィールド名: 列インデックス} を返す。

    例: headers = ["メニュー", "カロリー", ...], col_config = {"name": "メニュー", ...}
        → {"name": 0, "calories": 1, ...}

    name フィールドが見つからない場合は先頭列（インデックス0）をデフォルト使用。
    """
    col_map: dict[str, int] = {}
    for field, label in col_config.items():
        norm = normalize_header(label)
        # ヘッダーを正規化して部分一致で検索
        idx = next(
            (i for i, h in enumerate(headers) if norm in normalize_header(str(h))),
            -1,
        )
        if idx == -1:
            print(f"  警告: 列 '{label}' ({field}) が見つかりません")
        col_map[field] = idx

    # name 列が見つからなければ先頭列（0）をフォールバックとして使用
    if col_map.get("name", -1) == -1:
        col_map["name"] = 0

    return col_map


# ── Excel パーサー ─────────────────────────────────────

def parse_excel(file_path: str, chain_id: str, chain_config: dict) -> list[dict]:
    """
    Excel ファイルから栄養データを抽出する。

    処理の流れ:
      1. シート全体を文字列として読み込む（dtype=str で型変換を防ぐ）
      2. "エネルギー" or "カロリー" 列を探してヘッダー行を自動検出
      3. ヘッダー行以降を再読み込みして DataFrame を作成
      4. 各行をループして MenuItem 形式の dict に変換
    """
    col_config = chain_config["columns"]
    chain_name = chain_config["name"]
    default_category = chain_config.get("category", "")
    source_url = chain_config.get("file_url", "")

    sheet = chain_config.get("sheet", 0)
    skip_rows = chain_config.get("skip_rows", 0)

    # ── ステップ1: ヘッダー行を探すために全体を一旦読み込む ──
    raw_df = pd.read_excel(
        file_path,
        sheet_name=sheet,
        header=None,      # ヘッダー行を自動解釈させない
        skiprows=skip_rows,
        dtype=str,        # すべてのセルを文字列として読み込む
    )

    # ── ステップ2: ヘッダー行を検出 ──
    header_row_idx = chain_config.get("header_row")
    if header_row_idx is None:
        # エネルギー/カロリー列でヘッダーを検出（メニュー名列より安定）
        detect_label = col_config.get("calories", "エネルギー")
        header_row_idx = _detect_header_row_excel(raw_df, detect_label)
    if header_row_idx is None:
        raise ValueError(
            f"ヘッダー行が見つかりません（期待: '{col_config.get('calories', 'エネルギー')}'）"
        )

    print(f"  ヘッダー検出: 行 {header_row_idx}")

    # ── ステップ3: ヘッダー行を指定して再読み込み ──
    df = pd.read_excel(
        file_path,
        sheet_name=sheet,
        header=header_row_idx + skip_rows,
        dtype=str,
    )

    # 列名を正規化してマッピングを構築
    normalized_cols = {normalize_header(c): c for c in df.columns}
    col_map: dict[str, str] = {}
    for field, label in col_config.items():
        norm = normalize_header(label)
        # 完全一致優先、なければ部分一致
        matched = normalized_cols.get(norm) or next(
            (c for n, c in normalized_cols.items() if norm in n), None
        )
        if matched:
            col_map[field] = matched
        else:
            print(f"  警告: 列 '{label}' ({field}) が見つかりません")

    if "name" not in col_map:
        col_map["name"] = df.columns[0]

    # ── ステップ4: 各行をパースして dict に変換 ──
    items = []
    for _, row in df.iterrows():
        name_val = row.get(col_map["name"])
        if pd.isna(name_val) or str(name_val).strip() == "":
            continue
        name = str(name_val).strip().replace("\n", "")

        def get_float(field: str) -> float | None:
            col = col_map.get(field)
            if col is None:
                return None
            return parse_float(row.get(col))

        calories = get_float("calories")
        if calories is None:
            continue  # カロリー不明の行はスキップ（単位行など）

        item: dict = {
            "id": f"{chain_id}_{name}",
            "chain": chain_name,
            "category": default_category,
            "name": name,
            "calories": calories,
            "protein": get_float("protein") or 0.0,
            "fat": get_float("fat") or 0.0,
            "carbs": get_float("carbs") or 0.0,
        }
        salt = get_float("salt")
        if salt is not None:
            item["salt"] = salt
        item["sourceUrl"] = source_url
        items.append(item)

    print(f"  {len(items)} 件取得")
    return items


def _detect_header_row_excel(df: pd.DataFrame, detect_label: str) -> int | None:
    """DataFrame の各行を走査してヘッダー行のインデックスを返す"""
    normalized_target = normalize_header(detect_label)
    for i, row in df.iterrows():
        for cell in row:
            if normalized_target in normalize_header(cell):
                return int(i)
    return None


# ── PDF パーサー ───────────────────────────────────────

def parse_pdf(file_path: str, chain_id: str, chain_config: dict) -> list[dict]:
    """
    pdfplumber で PDF から栄養データを抽出する。

    複数テーブル対応:
      1ページに複数テーブルがある場合（CoCo壱番屋など）でも
      テーブルごとに独立して処理するため正確に解析できる。

    category_col オプション:
      指定した場合、データ行のその列の値をカテゴリとして使用する。
      すき家のように「カテゴリー」列が別に存在するケースに対応。
      None（結合セル）は直前の値で埋める（前方補完）。

    size_col オプション:
      指定した場合、メニュー名に " サイズ名" を付加する。
      例: "牛丼" + "並盛" → "牛丼 並盛"
    """
    col_config = chain_config["columns"]
    chain_name = chain_config["name"]
    default_category = chain_config.get("category", "")
    source_url = chain_config.get("file_url", "")

    # オプション設定の取得
    category_col_label = chain_config.get("category_col")  # 例: "カテゴリー"
    size_col_label = chain_config.get("size_col")           # 例: "サイズ"

    # ヘッダー検出キー: エネルギー/カロリー列の有無でヘッダー行を判定
    detect_label = col_config.get("calories", "エネルギー")
    normalized_detect = normalize_header(detect_label)

    # ── 全ページのテーブルを収集（テーブルごとに独立した list として保持）──
    all_tables: list[list[list]] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            # extract_tables() は1ページ内の全テーブルを返す
            all_tables.extend(page.extract_tables())

    if not all_tables:
        raise ValueError("PDFからテーブルを抽出できませんでした")

    items: list[dict] = []
    detected_count = 0  # ヘッダーが見つかったテーブル数のカウント

    for table in all_tables:
        if not table:
            continue

        # ── このテーブルのヘッダー行を検出 ──
        # "カロリー" や "エネルギー" が含まれる行をヘッダーとみなす
        header_idx = next(
            (
                i for i, row in enumerate(table)
                if any(
                    normalized_detect in normalize_header(str(c))
                    for c in row if c
                )
            ),
            -1,
        )
        if header_idx == -1:
            continue  # 栄養テーブルでなければスキップ

        detected_count += 1
        headers = table[header_idx]

        # ── カテゴリの決定方法を選択 ──
        if category_col_label:
            # category_col が指定されている場合: データ行から列の値を取得
            # テーブルヘッダーは使わず、後のループで行ごとに取得する
            table_default_category = default_category
            # category_col のインデックスを特定
            cat_idx = next(
                (i for i, h in enumerate(headers)
                 if normalize_header(category_col_label) in normalize_header(str(h))),
                -1,
            )
        else:
            # category_col が未指定: テーブルの1列目ヘッダーをカテゴリとして使用
            # 例: CoCo壱番屋の "辛口メニュー"、"トッピング" など
            raw_cat = str(headers[0]).strip().replace("\n", "") if headers[0] else ""
            table_default_category = raw_cat if raw_cat else default_category
            cat_idx = -1

        # size_col のインデックスを特定
        size_idx = -1
        if size_col_label:
            size_idx = next(
                (i for i, h in enumerate(headers)
                 if normalize_header(size_col_label) in normalize_header(str(h))),
                -1,
            )

        # 栄養値列のインデックスマップを構築
        col_map = build_col_map_from_headers(headers, col_config)

        # ── データ行のパース ──
        # 前方補完用: カテゴリとメニュー名の直前の値を保持する変数
        last_category = table_default_category
        last_name = ""  # メニュー名の前方補完用（結合セルの None を埋める）

        for row in table[header_idx + 1:]:
            name_idx = col_map["name"]
            if len(row) <= name_idx:
                continue

            # ── メニュー名の前方補完 ──
            # 結合セル（None）や空文字の場合は直前のメニュー名を継続して使用する
            # 例: 「牛丼 ミニ」「牛丼 並盛」の「牛丼」が複数行にわたるケース
            raw_name = row[name_idx]
            if raw_name and str(raw_name).strip():
                last_name = str(raw_name).strip().replace("\n", "")
            name = last_name
            if not name:
                continue  # テーブル先頭で名前がまだ確定していない行はスキップ

            # ── カテゴリの前方補完 ──
            # 結合セルは pdfplumber が None として返すため、
            # None の場合は直前の有効な値を継続して使用する
            if cat_idx != -1 and cat_idx < len(row):
                cat_val = row[cat_idx]
                if cat_val and str(cat_val).strip():
                    last_category = str(cat_val).strip().replace("\n", "")
                # None や空文字の場合は last_category をそのまま使う

            # ── サイズ付与 ──
            # size_col が指定されている場合、メニュー名にサイズを付加する
            # 例: "牛丼" + "並盛" → "牛丼 並盛"
            if size_idx != -1 and size_idx < len(row):
                size_val = row[size_idx]
                if size_val and str(size_val).strip():
                    name = f"{name} {str(size_val).strip()}"

            def get_val(field: str, _row=row, _col_map=col_map) -> float | None:
                """指定フィールドの列インデックスを引いて parse_float を呼ぶ"""
                idx = _col_map.get(field, -1)
                if idx == -1 or idx >= len(_row):
                    return None
                return parse_float(_row[idx])

            calories = get_val("calories")
            if calories is None:
                continue  # カロリーが取れない行はヘッダーや単位行なのでスキップ

            item: dict = {
                "id": f"{chain_id}_{name}",
                "chain": chain_name,
                "category": last_category,
                "name": name,
                "calories": calories,
                "protein": get_val("protein") or 0.0,
                "fat": get_val("fat") or 0.0,
                "carbs": get_val("carbs") or 0.0,
            }
            salt = get_val("salt")
            if salt is not None:
                item["salt"] = salt
            item["sourceUrl"] = source_url
            items.append(item)

    if detected_count == 0:
        raise ValueError(
            f"ヘッダー行が見つかりません（検出キー: '{detect_label}'）"
        )

    print(f"  テーブル {detected_count} 個を処理、{len(items)} 件取得")
    return items


# ── メイン処理 ─────────────────────────────────────────

def parse_chain(chain_id: str, chain_config: dict) -> list[dict]:
    """
    1チェーン分のファイルを取得・パースして MenuItem のリストを返す。

    file_url の拡張子を見て Excel か PDF かを自動判別し、
    対応するパーサー関数に処理を委譲する。
    """
    file_url = chain_config["file_url"]
    # クエリ文字列（?以降）を除去してから拡張子を取得
    ext = Path(file_url.split("?")[0]).suffix.lower()

    if ext in EXCEL_EXTS:
        suffix, parser = ext, parse_excel
    elif ext in PDF_EXTS:
        suffix, parser = ".pdf", parse_pdf
    else:
        raise ValueError(f"未対応のファイル形式: {ext}（xlsx / xls / pdf のみ対応）")

    print(f"  ダウンロード中: {file_url}")

    # NamedTemporaryFile: 一時ファイルを作成する（finally で必ず削除）
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name

    try:
        download_file(file_url, tmp_path)
        print(f"  パース中 ({suffix}) ...")
        return parser(tmp_path, chain_id, chain_config)
    finally:
        # 成功・失敗どちらでも一時ファイルを削除する
        os.unlink(tmp_path)


def load_existing(chain_id: str) -> list[dict]:
    """既存の JSON データを読み込む（ファイルが存在しなければ空リストを返す）"""
    path = DATA_DIR / f"{chain_id}.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_data(chain_id: str, items: list[dict]) -> None:
    """データを JSON ファイルに保存する（ensure_ascii=False で日本語をそのまま出力）"""
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"{chain_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"  保存: {path}")


def main() -> int:
    """
    エントリーポイント。chains.json を読み込んで全チェーンを処理する。
    失敗したチェーンは前回データを保持してスキップ（他のチェーンの処理は継続）。
    戻り値: 全成功なら 0、1件でも失敗なら 1（GitHub Actions の終了コードに使用）
    """
    with open(CHAINS_FILE, encoding="utf-8") as f:
        chains = json.load(f)

    success_count = 0
    fail_count = 0

    for chain_id, chain_config in chains.items():
        print(f"\n[{chain_config['name']}] 処理開始")
        try:
            items = parse_chain(chain_id, chain_config)
            save_data(chain_id, items)
            success_count += 1
        except Exception as e:
            fail_count += 1
            print(f"  エラー: {e}")
            traceback.print_exc()
            # 失敗時は既存データを上書きせず保持する
            existing = load_existing(chain_id)
            if existing:
                print(f"  前回データ ({len(existing)} 件) を保持します")
            else:
                print(f"  既存データなし。data/{chain_id}.json はスキップされます")

    print(f"\n完了: 成功 {success_count} 件 / 失敗 {fail_count} 件")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
