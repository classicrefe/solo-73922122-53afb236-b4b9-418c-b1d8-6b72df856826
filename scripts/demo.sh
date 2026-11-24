#!/usr/bin/env bash
# 演示脚本：对运行中的服务（默认 http://localhost:8000）走一遍关键操作。
# 也可以在 Swagger UI（/docs）里手工执行同样的调用。
set -euo pipefail
BASE="${1:-http://localhost:8000}"

step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }

step "1. 登记初始对照表（一个旧码可对应多个新码）"
curl -sS -X PUT "$BASE/legend" -H 'Content-Type: application/json' -d '{
  "mapping": {
    "01": ["0101", "0103"],
    "02": ["0201", "0202"],
    "03": ["0301", "0302"]
  }
}'; echo

step "2. 登记两幅旧图的旧地类像元数"
curl -sS -X PUT "$BASE/sheets/J50G001001/old-counts" -H 'Content-Type: application/json' \
  -d '{"counts": {"01": 1000, "02": 500, "03": 800}}'; echo
curl -sS -X PUT "$BASE/sheets/J50G001002/old-counts" -H 'Content-Type: application/json' \
  -d '{"counts": {"01": 400, "03": 600}}'; echo

step "3. 换表前查询：J50G001002 未复核，(01,0101) 给区间"
curl -sS "$BASE/overlap?sheet_id=J50G001002&old_code=01&new_code=0101"; echo

step "4. 外业补报 J50G001001 新地类 0101 整幅总数 600"
curl -sS -X PUT "$BASE/sheets/J50G001001/review-totals" -H 'Content-Type: application/json' \
  -d '{"totals": {"0101": 600}}'; echo

step "5. 复核后查询：0101 只能来自 01，(01,0101) 为确数 600"
curl -sS "$BASE/overlap?sheet_id=J50G001001&old_code=01&new_code=0101"; echo
curl -sS "$BASE/overlap?sheet_id=J50G001001&old_code=01&new_code=0103"; echo

step "6. 复核数更正：0101 改为 650"
curl -sS -X PUT "$BASE/sheets/J50G001001/review-totals" -H 'Content-Type: application/json' \
  -d '{"totals": {"0101": 650}}'; echo
curl -sS "$BASE/overlap?sheet_id=J50G001001&old_code=01&new_code=0101"; echo

step "7. 换表核对期间仍可登记复核数（J50G001002 补报 0301=100）"
curl -sS -X PUT "$BASE/sheets/J50G001002/review-totals" -H 'Content-Type: application/json' \
  -d '{"totals": {"0301": 100}}'; echo

step "8. 整表换对照表：01 新增 0102，03 新增 0305"
curl -sS -X PUT "$BASE/legend" -H 'Content-Type: application/json' -d '{
  "mapping": {
    "01": ["0101", "0102", "0103"],
    "02": ["0201", "0202"],
    "03": ["0301", "0302", "0305"]
  }
}'; echo

step "9. 换表后查询：同一图幅同一旧码，(01,0102) 从恒 0 变为区间"
curl -sS "$BASE/overlap?sheet_id=J50G001001&old_code=01&new_code=0102"; echo
curl -sS "$BASE/overlap?sheet_id=J50G001002&old_code=03&new_code=0305"; echo

step "10. 非法换表：删掉 03 林地 -> 409，列出受影响图幅，整次拒绝"
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' -X PUT "$BASE/legend" \
  -H 'Content-Type: application/json' \
  -d '{"mapping": {"01": ["0101"], "02": ["0201"]}}'
curl -sS -X PUT "$BASE/legend" -H 'Content-Type: application/json' \
  -d '{"mapping": {"01": ["0101"], "02": ["0201"]}}'; echo

step "11. 非法复核：复核数超过图幅总数 -> 409，原数据不变"
curl -sS -X PUT "$BASE/sheets/J50G001001/review-totals" -H 'Content-Type: application/json' \
  -d '{"totals": {"0101": 99999}}'; echo
curl -sS "$BASE/sheets/J50G001001"; echo

step "12. 确认坏换表未生效：对照表仍是第 8 步的版本"
curl -sS "$BASE/legend"; echo
