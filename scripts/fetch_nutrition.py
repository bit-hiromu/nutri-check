"""
栄養成分PDF自動取得スクリプト
chains.json に定義されたチェーン店のPDFをダウンロードし、
栄養データをパースして data/{chain_id}.json に出力する。
"""

import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

import pdfplumber
import requests

# プロジェクトルートからの相対パス
ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
CHAINS_FILE = Path(__file__).parent / "chains.json"


def download_pdf(url: str, dest_path: str) -> None:
    """PDFをURLからダウンロードして保存する"""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; NutriCheckBot/1.0)"}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    with open(dest_path, "wb") as f:
        f.write(response.content)


def normalize_header(text: str) -> str:
    """ヘッダー文字列を正規化（空白・改行・単位表記を除去）"""
    if text is None:
        return ""
    # 括弧内の単位（例: (kcal)、（g））を除去
    import re
    text = re.sub(r"[（(][^）)]*[）)]", "", text)
    return text.strip().replace("\n", "").replace(" ", "").replace("　", "")


def find_column_index(headers: list, target: str) -> int:
    """ヘッダーリストから対象列のインデックスを返す。見つからなければ -1"""
    normalized_target = normalize_header(target)
    for i, h in enumerate(headers):
        if normalized_target in normalize_header(str(h)):
            return i
    return -1


def parse_float(value) -> float | None:
    """セルの値を float に変換する。変換不能なら None を返す"""
    if value is None:
        return None
    text = str(value).strip().replace("－", "").replace("-", "").replace("−", "")
    if text == "" or text == "0":
        return 0.0
    try:
        return float(text)
    except ValueError:
        return None


def extract_tables_from_pdf(pdf_path: str) -> list[list]:
    """pdfplumber で全ページのテーブルを結合して返す"""
    all_rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                all_rows.extend(table)
    return all_rows


def find_header_row(rows: list[list], col_config: dict) -> int:
    """
    栄養成分のヘッダー行インデックスを返す。
    col_config の "name" キーの値がいずれかの列に含まれている行を探す。
    """
    name_key = col_config.get("name", "メニュー名")
    for i, row in enumerate(rows):
        for cell in row:
            if cell and normalize_header(name_key) in normalize_header(str(cell)):
                return i
    return -1


def parse_chain(chain_id: str, chain_config: dict) -> list[dict]:
    """
    1チェーンのPDFをパースして MenuItem のリストを返す。
    失敗した場合は例外を raise する。
    """
    pdf_url = chain_config["pdf_url"]
    col_config = chain_config["columns"]
    chain_name = chain_config["name"]
    category = chain_config.get("category", "")

    print(f"  ダウンロード中: {pdf_url}")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        download_pdf(pdf_url, tmp_path)
        print(f"  パース中 ...")
        rows = extract_tables_from_pdf(tmp_path)
    finally:
        os.unlink(tmp_path)

    if not rows:
        raise ValueError("PDFからテーブルを抽出できませんでした")

    # ヘッダー行を検出
    header_idx = find_header_row(rows, col_config)
    if header_idx == -1:
        raise ValueError(f"ヘッダー行が見つかりません（期待: '{col_config.get('name')}'）")

    headers = rows[header_idx]
    print(f"  ヘッダー検出 (行{header_idx}): {[str(h)[:20] for h in headers]}")

    # 各列のインデックスを解決
    col_idx = {}
    for field, label in col_config.items():
        idx = find_column_index(headers, label)
        if idx == -1:
            print(f"  警告: 列 '{label}' ({field}) が見つかりません")
        col_idx[field] = idx

    if col_idx.get("name", -1) == -1:
        raise ValueError("メニュー名列が見つかりません")

    # データ行をパース
    items = []
    for row in rows[header_idx + 1:]:
        if len(row) <= col_idx["name"]:
            continue

        name_val = row[col_idx["name"]]
        if not name_val or str(name_val).strip() == "":
            continue  # 空行をスキップ

        name = str(name_val).strip().replace("\n", "")

        def get_float(field: str) -> float | None:
            idx = col_idx.get(field, -1)
            if idx == -1 or idx >= len(row):
                return None
            return parse_float(row[idx])

        calories = get_float("calories")
        protein = get_float("protein")
        fat = get_float("fat")
        carbs = get_float("carbs")

        # カロリーが取得できない行はスキップ
        if calories is None:
            continue

        item: dict = {
            "id": f"{chain_id}_{name}",
            "chain": chain_name,
            "category": category,
            "name": name,
            "calories": calories,
            "protein": protein if protein is not None else 0.0,
            "fat": fat if fat is not None else 0.0,
            "carbs": carbs if carbs is not None else 0.0,
        }

        salt = get_float("salt")
        if salt is not None:
            item["salt"] = salt

        source_url = chain_config.get("source_url", pdf_url)
        item["sourceUrl"] = source_url

        items.append(item)

    print(f"  {len(items)} 件取得")
    return items


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
            # 失敗時は既存データを保持（上書きしない）
            existing = load_existing(chain_id)
            if existing:
                print(f"  前回データ ({len(existing)} 件) を保持します")
            else:
                print(f"  既存データなし。data/{chain_id}.json はスキップされます")

    print(f"\n完了: 成功 {success_count} 件 / 失敗 {fail_count} 件")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
