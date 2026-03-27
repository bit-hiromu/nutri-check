"""
栄養成分データ自動取得スクリプト
chains.json に定義されたチェーン店の Excel または PDF をダウンロードし、
栄養データをパースして data/{chain_id}.json に出力する。

対応フォーマット:
  - Excel (.xlsx / .xls): pandas + openpyxl で解析（推奨）
  - PDF (.pdf): pdfplumber で解析

ヘッダー検出:
  「エネルギー」列（calories）の存在でヘッダー行を特定する。
  「メニュー名」列が存在しない場合は最初の列をメニュー名として使用。
  1ファイルに複数テーブルがある場合は各テーブルを独立して処理し、
  テーブルの1列目ヘッダーをカテゴリ名として自動取得する。
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

# プロジェクトルートからの相対パス
ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
CHAINS_FILE = Path(__file__).parent / "chains.json"

EXCEL_EXTS = {".xlsx", ".xls"}
PDF_EXTS = {".pdf"}


# ---------------------------------------------------------------------------
# 共通ユーティリティ
# ---------------------------------------------------------------------------

def download_file(url: str, dest_path: str) -> None:
    """ファイルをURLからダウンロードして保存する"""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; NutriCheckBot/1.0)"}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    with open(dest_path, "wb") as f:
        f.write(response.content)


def normalize_header(text) -> str:
    """
    ヘッダー文字列を正規化する。
    - 括弧内の単位（例: (kcal)、（g））を除去
    - 空白・改行・全角スペースを除去
    """
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    text = str(text)
    text = re.sub(r"[（(][^）)]*[）)]", "", text)
    return text.strip().replace("\n", "").replace(" ", "").replace("　", "")


def parse_float(value) -> float | None:
    """セルの値を float に変換する。変換不能なら None を返す"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if not pd.isna(value) else None
    text = str(value).strip()
    # ハイフン類（欠損値表記）は 0 扱い
    text = re.sub(r"^[－\-−‐‑]$", "0", text)
    # カンマ区切り数値（例: 1,116）に対応
    text = text.replace(",", "")
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def build_col_map_from_headers(headers: list, col_config: dict) -> dict[str, int]:
    """
    ヘッダーリストと設定から {フィールド名: 列インデックス} のマップを返す。
    name フィールドが見つからない場合は列 0 をデフォルトとして使用する。
    """
    col_map: dict[str, int] = {}
    for field, label in col_config.items():
        norm = normalize_header(label)
        idx = next(
            (i for i, h in enumerate(headers) if norm in normalize_header(str(h))),
            -1,
        )
        if idx == -1:
            print(f"  警告: 列 '{label}' ({field}) が見つかりません")
        col_map[field] = idx

    # name 列が見つからなければ先頭列を使用
    if col_map.get("name", -1) == -1:
        col_map["name"] = 0

    return col_map


# ---------------------------------------------------------------------------
# Excel パーサー
# ---------------------------------------------------------------------------

def parse_excel(file_path: str, chain_id: str, chain_config: dict) -> list[dict]:
    """
    Excel ファイルから栄養データを抽出する。

    chains.json の設定:
      sheet      : シート名またはインデックス（省略時は 0）
      header_row : ヘッダー行番号（0始まり、省略時は自動検出）
      skip_rows  : 先頭スキップ行数（省略時は 0）
    """
    col_config = chain_config["columns"]
    chain_name = chain_config["name"]
    default_category = chain_config.get("category", "")
    source_url = chain_config.get("file_url", "")

    sheet = chain_config.get("sheet", 0)
    skip_rows = chain_config.get("skip_rows", 0)

    # シート全体を文字列として読み込みヘッダー行を自動検出
    raw_df = pd.read_excel(
        file_path,
        sheet_name=sheet,
        header=None,
        skiprows=skip_rows,
        dtype=str,
    )

    header_row_idx = chain_config.get("header_row")
    if header_row_idx is None:
        # エネルギー列でヘッダー行を検出（メニュー名より確実）
        detect_label = col_config.get("calories", "エネルギー")
        header_row_idx = _detect_header_row_excel(raw_df, detect_label)
    if header_row_idx is None:
        raise ValueError(
            f"ヘッダー行が見つかりません（期待: '{col_config.get('calories', 'エネルギー')}'）"
        )

    print(f"  ヘッダー検出: 行 {header_row_idx}")

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
        matched = normalized_cols.get(norm) or next(
            (c for n, c in normalized_cols.items() if norm in n), None
        )
        if matched:
            col_map[field] = matched
        else:
            print(f"  警告: 列 '{label}' ({field}) が見つかりません")

    # name 列が見つからなければ先頭列を使用
    if "name" not in col_map:
        col_map["name"] = df.columns[0]

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
            continue

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
    """DataFrame の中からヘッダー行インデックスを自動検出する"""
    normalized_target = normalize_header(detect_label)
    for i, row in df.iterrows():
        for cell in row:
            if normalized_target in normalize_header(cell):
                return int(i)
    return None


# ---------------------------------------------------------------------------
# PDF パーサー
# ---------------------------------------------------------------------------

def parse_pdf(file_path: str, chain_id: str, chain_config: dict) -> list[dict]:
    """
    pdfplumber で PDF から栄養データを抽出する。

    各テーブルを独立して処理し、テーブルの1列目ヘッダーをカテゴリ名として使用する。
    ヘッダー行は「エネルギー」列の存在で検出する（メニュー名より確実）。
    """
    col_config = chain_config["columns"]
    chain_name = chain_config["name"]
    default_category = chain_config.get("category", "")
    source_url = chain_config.get("file_url", "")

    # ヘッダー検出に使うラベル（エネルギー列が最も安定）
    detect_label = col_config.get("calories", "エネルギー")
    normalized_detect = normalize_header(detect_label)

    # 全ページのテーブルを個別に収集（マージしない）
    all_tables: list[list[list]] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            all_tables.extend(page.extract_tables())

    if not all_tables:
        raise ValueError("PDFからテーブルを抽出できませんでした")

    items: list[dict] = []
    detected_count = 0

    for table in all_tables:
        if not table:
            continue

        # このテーブル内のヘッダー行を検出
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

        # 1列目ヘッダーをカテゴリ名として取得（例: "辛口メニュー"）
        raw_category = str(headers[0]).strip().replace("\n", "") if headers[0] else ""
        category = raw_category if raw_category else default_category

        col_map = build_col_map_from_headers(headers, col_config)

        for row in table[header_idx + 1:]:
            name_idx = col_map["name"]
            if len(row) <= name_idx or not row[name_idx]:
                continue
            name = str(row[name_idx]).strip().replace("\n", "")
            if not name:
                continue

            def get_val(field: str, _row=row, _col_map=col_map) -> float | None:
                idx = _col_map.get(field, -1)
                if idx == -1 or idx >= len(_row):
                    return None
                return parse_float(_row[idx])

            calories = get_val("calories")
            if calories is None:
                continue

            item: dict = {
                "id": f"{chain_id}_{name}",
                "chain": chain_name,
                "category": category,
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


# ---------------------------------------------------------------------------
# メイン処理
# ---------------------------------------------------------------------------

def parse_chain(chain_id: str, chain_config: dict) -> list[dict]:
    """
    1チェーンのファイルを取得・パースして MenuItem のリストを返す。
    file_url の拡張子で Excel / PDF を自動判別する。
    """
    file_url = chain_config["file_url"]
    ext = Path(file_url.split("?")[0]).suffix.lower()

    if ext in EXCEL_EXTS:
        suffix, parser = ext, parse_excel
    elif ext in PDF_EXTS:
        suffix, parser = ".pdf", parse_pdf
    else:
        raise ValueError(f"未対応のファイル形式: {ext}（xlsx / xls / pdf のみ対応）")

    print(f"  ダウンロード中: {file_url}")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name

    try:
        download_file(file_url, tmp_path)
        print(f"  パース中 ({suffix}) ...")
        return parser(tmp_path, chain_id, chain_config)
    finally:
        os.unlink(tmp_path)


def load_existing(chain_id: str) -> list[dict]:
    """既存のJSONデータを読み込む（存在しなければ空リスト）"""
    path = DATA_DIR / f"{chain_id}.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_data(chain_id: str, items: list[dict]) -> None:
    """データをJSONファイルに保存する"""
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"{chain_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"  保存: {path}")


def main() -> int:
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
            existing = load_existing(chain_id)
            if existing:
                print(f"  前回データ ({len(existing)} 件) を保持します")
            else:
                print(f"  既存データなし。data/{chain_id}.json はスキップされます")

    print(f"\n完了: 成功 {success_count} 件 / 失敗 {fail_count} 件")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
