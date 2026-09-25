from __future__ import annotations

import argparse
import sqlite3
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_XLSX_PATH = ROOT_DIR / "community_table" / "micro_community_final.xlsx"
DEFAULT_DB_PATH = ROOT_DIR / "server" / "ninganju_auth.db"

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"main": MAIN_NS, "rel": REL_NS, "pkg": PACKAGE_REL_NS}

REQUIRED_HEADERS = {
    "ID",
    "租赁标准价格",
    "公寓下限",
    "公寓上限",
    "居民楼上限",
    "居民楼下限",
    "均价",
    "两居室下限",
    "两居室上限",
    "公寓中位数",
    "一居室中位数",
    "二居室中位数",
    "微社区编号",
    "Micro_community_name",
    "wgs_lng",
    "wgs_lat",
    "OBJECTID",
    "风景名胜数量",
    "体育休闲设施数量",
    "科教文化设施数量",
    "购物设施数量",
    "生活设施数量",
    "医疗设施数量",
    "餐饮店数量",
    "微社区编号_2",
    "微社区名称",
    "风景名胜数量_指数",
    "体育休闲设施数量_指数",
    "科教文化设施数量_指数",
    "购物设施数量_指数",
    "生活设施数量_指数",
    "医疗设施数量_指数",
    "餐饮店数量_指数",
    "Score",
    "gcj02_lng",
    "gcj02_lat",
    "convert_status",
}

TABLE_COLUMNS = (
    "source_row_number",
    "source_id",
    "rent_standard_price",
    "apartment_rent_min",
    "apartment_rent_max",
    "one_bedroom_rent_min",
    "one_bedroom_rent_max",
    "average_house_price",
    "two_bedroom_rent_min",
    "two_bedroom_rent_max",
    "apartment_rent_median",
    "one_bedroom_rent_median",
    "two_bedroom_rent_median",
    "community_id",
    "community_name",
    "wgs_lng",
    "wgs_lat",
    "object_id",
    "poi_scenic_count",
    "poi_sports_leisure_count",
    "poi_science_education_culture_count",
    "poi_shopping_count",
    "poi_life_service_count",
    "poi_medical_count",
    "poi_restaurant_count",
    "poi_scenic_index",
    "poi_sports_leisure_index",
    "poi_science_education_culture_index",
    "poi_shopping_index",
    "poi_life_service_index",
    "poi_medical_index",
    "poi_restaurant_index",
    "poi_score",
    "gcj02_lng",
    "gcj02_lat",
    "convert_status",
    "source_filename",
    "source_sheet",
    "imported_at",
)


def column_index(cell_reference: str) -> int:
    letters = "".join(character for character in cell_reference if character.isalpha())
    result = 0
    for character in letters.upper():
        result = result * 26 + ord(character) - ord("A") + 1
    return result - 1


def numeric_value(raw_value: str | None) -> int | float | None:
    if raw_value is None or raw_value == "":
        return None
    value = float(raw_value)
    return int(value) if value.is_integer() else value


def shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(node.text or "" for node in item.findall(".//main:t", NS)) for item in root]


def first_worksheet(archive: zipfile.ZipFile) -> tuple[str, str]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    first_sheet = workbook.find("main:sheets/main:sheet", NS)
    if first_sheet is None:
        raise ValueError("XLSX 中没有工作表")

    sheet_name = first_sheet.attrib.get("name", "Sheet1")
    relationship_id = first_sheet.attrib[f"{{{REL_NS}}}id"]
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    relationship = relationships.find(f"pkg:Relationship[@Id='{relationship_id}']", NS)
    if relationship is None:
        raise ValueError(f"无法找到工作表 {sheet_name} 的关系定义")

    target = relationship.attrib["Target"].lstrip("/")
    worksheet_path = target if target.startswith("xl/") else f"xl/{target}"
    return sheet_name, worksheet_path


def worksheet_rows(xlsx_path: Path) -> tuple[str, list[list[Any]]]:
    with zipfile.ZipFile(xlsx_path) as archive:
        strings = shared_strings(archive)
        sheet_name, worksheet_path = first_worksheet(archive)
        worksheet = ET.fromstring(archive.read(worksheet_path))

        rows: list[list[Any]] = []
        for row_node in worksheet.findall("main:sheetData/main:row", NS):
            values: dict[int, Any] = {}
            for cell in row_node.findall("main:c", NS):
                reference = cell.attrib.get("r", "")
                index = column_index(reference)
                cell_type = cell.attrib.get("t", "n")
                value_node = cell.find("main:v", NS)

                if cell_type == "inlineStr":
                    value: Any = "".join(
                        node.text or "" for node in cell.findall("main:is//main:t", NS)
                    )
                elif cell_type == "s":
                    value = strings[int(value_node.text)] if value_node is not None and value_node.text else ""
                elif cell_type == "b":
                    value = bool(int(value_node.text)) if value_node is not None and value_node.text else False
                elif cell_type in {"str", "e"}:
                    value = value_node.text if value_node is not None else ""
                else:
                    value = numeric_value(value_node.text if value_node is not None else None)
                values[index] = value

            width = max(values, default=-1) + 1
            rows.append([values.get(index) for index in range(width)])
    return sheet_name, rows


def required_text(value: Any, field_name: str, excel_row: int) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"第 {excel_row} 行缺少必填字段：{field_name}")
    return text


def required_number(value: Any, field_name: str, excel_row: int) -> float:
    if value is None or value == "":
        raise ValueError(f"第 {excel_row} 行缺少必填数值：{field_name}")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"第 {excel_row} 行的 {field_name} 不是有效数字：{value}") from exc


def optional_number(value: Any, field_name: str, excel_row: int) -> float | None:
    if value is None or value == "":
        return None
    return required_number(value, field_name, excel_row)


def integer_value(value: Any, field_name: str, excel_row: int) -> int:
    number = required_number(value, field_name, excel_row)
    if not number.is_integer():
        raise ValueError(f"第 {excel_row} 行的 {field_name} 应为整数：{value}")
    return int(number)


def values_by_header(row: list[Any], header_positions: dict[str, int]) -> dict[str, Any]:
    return {
        header: row[position] if position < len(row) else None
        for header, position in header_positions.items()
    }


def prepare_records(
    xlsx_path: Path, sheet_name: str, rows: list[list[Any]]
) -> tuple[list[tuple[Any, ...]], dict[str, int]]:
    if len(rows) < 2:
        raise ValueError("XLSX 没有可导入的数据行")

    headers = [str(value).strip() if value is not None else "" for value in rows[0]]
    header_positions = {header: index for index, header in enumerate(headers) if header}
    missing_headers = sorted(REQUIRED_HEADERS - set(header_positions))
    if missing_headers:
        raise ValueError(f"XLSX 缺少字段：{', '.join(missing_headers)}")

    imported_at = datetime.now(timezone.utc).isoformat()
    records: list[tuple[Any, ...]] = []
    seen_ids: set[str] = set()
    reversed_one_bedroom_bounds = 0
    duplicate_reference_mismatches = 0

    for excel_row, row in enumerate(rows[1:], start=2):
        values = values_by_header(row, header_positions)
        if all(value is None or value == "" for value in values.values()):
            continue

        community_id = required_text(values["微社区编号"], "微社区编号", excel_row)
        community_name = required_text(values["Micro_community_name"], "Micro_community_name", excel_row)
        if community_id in seen_ids:
            raise ValueError(f"微社区编号重复：{community_id}（第 {excel_row} 行）")
        seen_ids.add(community_id)

        reference_id = required_text(values.get("微社区编号_2"), "微社区编号_2", excel_row)
        reference_name = required_text(values.get("微社区名称"), "微社区名称", excel_row)
        if reference_id != community_id or reference_name != community_name:
            duplicate_reference_mismatches += 1

        one_bound_a = required_number(values["居民楼上限"], "居民楼上限", excel_row)
        one_bound_b = required_number(values["居民楼下限"], "居民楼下限", excel_row)
        if one_bound_a < one_bound_b:
            reversed_one_bedroom_bounds += 1
        one_bedroom_min = min(one_bound_a, one_bound_b)
        one_bedroom_max = max(one_bound_a, one_bound_b)

        wgs_lng = required_number(values["wgs_lng"], "wgs_lng", excel_row)
        wgs_lat = required_number(values["wgs_lat"], "wgs_lat", excel_row)
        gcj02_lng = required_number(values["gcj02_lng"], "gcj02_lng", excel_row)
        gcj02_lat = required_number(values["gcj02_lat"], "gcj02_lat", excel_row)
        if not (-180 <= wgs_lng <= 180 and -90 <= wgs_lat <= 90):
            raise ValueError(f"第 {excel_row} 行 WGS84 坐标超出范围")
        if not (-180 <= gcj02_lng <= 180 and -90 <= gcj02_lat <= 90):
            raise ValueError(f"第 {excel_row} 行 GCJ-02 坐标超出范围")

        rent_values = {
            field: required_number(values[field], field, excel_row)
            for field in (
                "公寓下限",
                "公寓上限",
                "两居室下限",
                "两居室上限",
                "公寓中位数",
                "一居室中位数",
                "二居室中位数",
            )
        }
        if any(number < 0 for number in rent_values.values()):
            raise ValueError(f"第 {excel_row} 行包含负数租金")

        record = (
            excel_row,
            integer_value(values["ID"], "ID", excel_row),
            optional_number(values["租赁标准价格"], "租赁标准价格", excel_row),
            rent_values["公寓下限"],
            rent_values["公寓上限"],
            one_bedroom_min,
            one_bedroom_max,
            optional_number(values["均价"], "均价", excel_row),
            rent_values["两居室下限"],
            rent_values["两居室上限"],
            rent_values["公寓中位数"],
            rent_values["一居室中位数"],
            rent_values["二居室中位数"],
            community_id,
            community_name,
            wgs_lng,
            wgs_lat,
            integer_value(values["OBJECTID"], "OBJECTID", excel_row),
            integer_value(values["风景名胜数量"], "风景名胜数量", excel_row),
            integer_value(values["体育休闲设施数量"], "体育休闲设施数量", excel_row),
            integer_value(values["科教文化设施数量"], "科教文化设施数量", excel_row),
            integer_value(values["购物设施数量"], "购物设施数量", excel_row),
            integer_value(values["生活设施数量"], "生活设施数量", excel_row),
            integer_value(values["医疗设施数量"], "医疗设施数量", excel_row),
            integer_value(values["餐饮店数量"], "餐饮店数量", excel_row),
            optional_number(values["风景名胜数量_指数"], "风景名胜数量_指数", excel_row),
            optional_number(values["体育休闲设施数量_指数"], "体育休闲设施数量_指数", excel_row),
            optional_number(values["科教文化设施数量_指数"], "科教文化设施数量_指数", excel_row),
            optional_number(values["购物设施数量_指数"], "购物设施数量_指数", excel_row),
            optional_number(values["生活设施数量_指数"], "生活设施数量_指数", excel_row),
            optional_number(values["医疗设施数量_指数"], "医疗设施数量_指数", excel_row),
            optional_number(values["餐饮店数量_指数"], "餐饮店数量_指数", excel_row),
            optional_number(values["Score"], "Score", excel_row),
            gcj02_lng,
            gcj02_lat,
            required_text(values["convert_status"], "convert_status", excel_row),
            xlsx_path.name,
            sheet_name,
            imported_at,
        )
        records.append(record)

    diagnostics = {
        "one_bedroom_bounds_normalized": reversed_one_bedroom_bounds,
        "duplicate_reference_mismatches": duplicate_reference_mismatches,
    }
    return records, diagnostics


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        create table if not exists micro_community (
            community_id text primary key,
            community_name text not null,
            source_row_number integer not null,
            source_id integer not null,
            rent_standard_price real,
            apartment_rent_min real not null check (apartment_rent_min >= 0),
            apartment_rent_max real not null check (apartment_rent_max >= apartment_rent_min),
            one_bedroom_rent_min real not null check (one_bedroom_rent_min >= 0),
            one_bedroom_rent_max real not null check (one_bedroom_rent_max >= one_bedroom_rent_min),
            average_house_price real,
            two_bedroom_rent_min real not null check (two_bedroom_rent_min >= 0),
            two_bedroom_rent_max real not null check (two_bedroom_rent_max >= two_bedroom_rent_min),
            apartment_rent_median real not null,
            one_bedroom_rent_median real not null,
            two_bedroom_rent_median real not null,
            wgs_lng real not null check (wgs_lng between -180 and 180),
            wgs_lat real not null check (wgs_lat between -90 and 90),
            object_id integer not null,
            poi_scenic_count integer not null,
            poi_sports_leisure_count integer not null,
            poi_science_education_culture_count integer not null,
            poi_shopping_count integer not null,
            poi_life_service_count integer not null,
            poi_medical_count integer not null,
            poi_restaurant_count integer not null,
            poi_scenic_index real,
            poi_sports_leisure_index real,
            poi_science_education_culture_index real,
            poi_shopping_index real,
            poi_life_service_index real,
            poi_medical_index real,
            poi_restaurant_index real,
            poi_score real,
            gcj02_lng real not null check (gcj02_lng between -180 and 180),
            gcj02_lat real not null check (gcj02_lat between -90 and 90),
            convert_status text not null,
            source_filename text not null,
            source_sheet text not null,
            imported_at text not null,
            unique (source_id),
            unique (object_id)
        );

        create index if not exists idx_micro_community_gcj02
            on micro_community(gcj02_lat, gcj02_lng);
        create index if not exists idx_micro_community_poi_score
            on micro_community(poi_score desc);
        create index if not exists idx_micro_community_apartment_rent
            on micro_community(apartment_rent_median);
        create index if not exists idx_micro_community_one_bedroom_rent
            on micro_community(one_bedroom_rent_median);
        create index if not exists idx_micro_community_two_bedroom_rent
            on micro_community(two_bedroom_rent_median);
        """
    )


def upsert_records(connection: sqlite3.Connection, records: Iterable[tuple[Any, ...]]) -> None:
    columns = ", ".join(TABLE_COLUMNS)
    placeholders = ", ".join("?" for _ in TABLE_COLUMNS)
    updates = ", ".join(
        f"{column} = excluded.{column}" for column in TABLE_COLUMNS if column != "community_id"
    )
    sql = f"""
        insert into micro_community ({columns})
        values ({placeholders})
        on conflict(community_id) do update set {updates}
    """
    connection.executemany(sql, records)


def backup_database(db_path: Path) -> Path:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{db_path.stem}_before_microcommunity_{timestamp}.db"
    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as destination:
        source.backup(destination)
    return backup_path


def verify_import(
    connection: sqlite3.Connection, expected_count: int, imported_at: str
) -> dict[str, Any]:
    summary = connection.execute(
        """
        select
            count(*) as total,
            count(distinct community_id) as unique_ids,
            sum(case when imported_at = ? then 1 else 0 end) as current_batch,
            sum(case when community_name = '' then 1 else 0 end) as blank_names,
            sum(case when convert_status <> 'OK' then 1 else 0 end) as non_ok_conversions,
            sum(case when apartment_rent_max < apartment_rent_min then 1 else 0 end) as bad_apartment_ranges,
            sum(case when one_bedroom_rent_max < one_bedroom_rent_min then 1 else 0 end) as bad_one_bedroom_ranges,
            sum(case when two_bedroom_rent_max < two_bedroom_rent_min then 1 else 0 end) as bad_two_bedroom_ranges
        from micro_community
        """,
        (imported_at,),
    ).fetchone()
    result = dict(summary)
    if result["current_batch"] != expected_count or result["total"] != result["unique_ids"]:
        raise RuntimeError(
            f"导入数量校验失败：本批期望 {expected_count}，本批实际 {result['current_batch']}，"
            f"全表 {result['total']}，唯一 ID {result['unique_ids']}"
        )
    if any(
        result[key]
        for key in (
            "blank_names",
            "bad_apartment_ranges",
            "bad_one_bedroom_ranges",
            "bad_two_bedroom_ranges",
        )
    ):
        raise RuntimeError(f"导入质量校验失败：{result}")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将宁安居微社区 XLSX 导入本地 SQLite")
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX_PATH, help="源 XLSX 文件")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="目标 SQLite 文件")
    parser.add_argument("--backup", action="store_true", help="导入前备份 SQLite 数据库")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    xlsx_path = args.xlsx.resolve()
    db_path = args.db.resolve()
    if not xlsx_path.is_file():
        print(f"源文件不存在：{xlsx_path}", file=sys.stderr)
        return 1
    if not db_path.is_file():
        print(f"SQLite 数据库不存在：{db_path}", file=sys.stderr)
        return 1

    sheet_name, rows = worksheet_rows(xlsx_path)
    records, diagnostics = prepare_records(xlsx_path, sheet_name, rows)
    if not records:
        print("没有可导入的记录", file=sys.stderr)
        return 1

    backup_path = backup_database(db_path) if args.backup else None
    connection = sqlite3.connect(db_path, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("pragma foreign_keys = on")
        connection.execute("begin immediate")
        create_schema(connection)
        upsert_records(connection, records)
        verification = verify_import(connection, len(records), str(records[0][-1]))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    print(f"XLSX：{xlsx_path}")
    print(f"工作表：{sheet_name}")
    print(f"SQLite：{db_path}")
    if backup_path:
        print(f"备份：{backup_path}")
    print(f"已导入/更新：{len(records)} 条")
    print(f"一居室上下限已按数值标准化：{diagnostics['one_bedroom_bounds_normalized']} 条")
    print(f"重复编号/名称列不一致：{diagnostics['duplicate_reference_mismatches']} 条")
    print(f"质量校验：{verification}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
