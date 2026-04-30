# 数据集快照对比工具

一个基于 Python + pandas + sqlite3 的数据集快照对比工具，支持 Schema 对齐、按主键找增删改、数值变化统计和 Markdown 报告生成。

## 目录

- [安装说明](#安装说明)
- [快速开始](#快速开始)
- [参数说明](#参数说明)
- [典型示例](#典型示例)
- [报告结构](#报告结构)
- [常见错误处理](#常见错误处理)
- [API 接口](#api-接口)

---

## 安装说明

### 环境要求

- Python 3.7+
- pip

### 安装步骤

1. 克隆或下载项目代码

2. 安装依赖：

```bash
pip install -r requirements.txt
```

### 依赖项

| 包名 | 版本要求 | 用途 |
|------|----------|------|
| pandas | >= 1.3.0 | 数据处理和分析 |
| pytest | >= 6.2.0 | 测试框架（开发用） |

---

## 快速开始

### 命令行方式

```bash
# 基本用法：对比 SQLite 中的两张表
python -m dataset_diff_reporter \
    --db ./data/mydb.db \
    --old-table sales_2023 \
    --new-table sales_2024 \
    --pk id \
    --output ./reports/diff_report.md
```

### Python API 方式

```python
import pandas as pd
import sqlite3
from dataset_diff_reporter import DatasetDiffReporter

# 方式1：从 SQLite 数据库对比
reporter = DatasetDiffReporter(primary_keys=['id'])
result = reporter.compare_from_sqlite(
    db_path='./data/mydb.db',
    table_name_old='sales_2023',
    table_name_new='sales_2024'
)

# 方式2：从 DataFrame 对比
df_old = pd.DataFrame({...})
df_new = pd.DataFrame({...})
result = reporter.compare_from_dataframes(df_old, df_new)

# 查看结果
print(result['report'])  # Markdown 报告
print(result['changes']['added'])   # 新增记录
print(result['changes']['removed']) # 删除记录
print(result['changes']['modified']) # 修改记录
```

---

## 参数说明

### 必需参数

| 参数 | 简写 | 说明 | 示例 |
|------|------|------|------|
| `--db` | 无 | SQLite 数据库文件路径 | `--db ./data/mydb.db` |
| `--old-table` | 无 | 旧数据表名（基准数据） | `--old-table table_v1` |
| `--new-table` | 无 | 新数据表名（对比数据） | `--new-table table_v2` |
| `--pk` | 无 | 主键列名（支持复合主键，多个列名用空格分隔） | `--pk id` 或 `--pk dept_id emp_id` |

### 可选参数

| 参数 | 简写 | 默认值 | 说明 | 示例 |
|------|------|--------|------|------|
| `--output` | `-o` | 无 | 输出文件路径，不指定则输出到控制台 | `-o ./report.md` |
| `--title` | 无 | "数据集快照对比报告" | 报告标题 | `--title "月度销售数据对比"` |
| `--ignore-columns` | 无 | 无 | 忽略比较的列名列表 | `--ignore-columns updated_at` |
| `--help` | `-h` | 无 | 显示帮助信息 | `--help` |

---

## 典型示例

### 示例1：基本对比

对比两张表并输出到控制台：

```bash
python -m dataset_diff_reporter \
    --db ./sales.db \
    --old-table sales_jan \
    --new-table sales_feb \
    --pk order_id
```

### 示例2：输出到文件

对比两张表并保存报告到文件：

```bash
python -m dataset_diff_reporter \
    --db ./sales.db \
    --old-table sales_jan \
    --new-table sales_feb \
    --pk order_id \
    --output ./reports/jan_vs_feb.md
```

### 示例3：使用复合主键

当表使用复合主键时（如：部门ID + 员工ID）：

```bash
python -m dataset_diff_reporter \
    --db ./hr.db \
    --old-table employees_2023 \
    --new-table employees_2024 \
    --pk department_id employee_id \
    --output ./reports/employee_diff.md
```

### 示例4：自定义报告标题

```bash
python -m dataset_diff_reporter \
    --db ./sales.db \
    --old-table sales_2023_q4 \
    --new-table sales_2024_q1 \
    --pk id \
    --title "2023Q4 vs 2024Q1 销售数据对比" \
    --output ./reports/q4_vs_q1.md
```

### 示例5：忽略指定列

忽略某些不需要比较的列（如更新时间、时间戳等）：

```bash
python -m dataset_diff_reporter \
    --db ./inventory.db \
    --old-table stock_2023 \
    --new-table stock_2024 \
    --pk sku \
    --ignore-columns updated_at last_sync_time \
    --output ./reports/stock_diff.md
```

### 示例6：完整示例

一个包含所有常用参数的完整示例：

```bash
python -m dataset_diff_reporter \
    --db ./ecommerce.db \
    --old-table products_2023 \
    --new-table products_2024 \
    --pk product_id \
    --title "2023 vs 2024 产品目录对比" \
    --ignore-columns created_at updated_at \
    --output ./reports/products_2023_vs_2024.md
```

---

## 报告结构

生成的 Markdown 报告包含以下部分：

### 1. 摘要 (Summary)

快速概览数据变化情况：

```markdown
# 数据集快照对比报告

## 摘要

- **新增记录**: 5 条
- **删除记录**: 3 条
- **修改记录**: 12 条
```

### 2. Schema 变化 (Schema Changes)

检测表结构的变化：

- **新增列**：新表中添加的列
- **删除列**：新表中移除的列
- **类型变化**：数据类型发生变化的列

示例：

```markdown
## Schema变化

### 新增列
- `discount_rate`
- `is_active`

### 删除列
- `old_price`

### 类型变化
- `price`: `INTEGER` → `REAL`
```

### 3. 数据变化详情 (Data Changes Details)

详细列出所有数据变化：

- **新增记录**：新表中有但旧表中没有的记录
- **删除记录**：旧表中有但新表中没有的记录
- **修改记录**：主键相同但其他字段值不同的记录

修改记录示例：

```markdown
### 修改记录

 id  price_old  price_new  name_old  name_new
  1      100.0      120.0  ProductA  ProductA
  2       50.0       50.0   ItemOld   ItemNew
```

### 4. 数值变化统计 (Numeric Statistics)

对数值类型列进行详细统计：

```markdown
## 数值变化统计

### 列: `price`

- **总行数**: 100
- **平均变化**: +15.5000
- **中位数变化**: +10.0000
- **最小变化**: -50.0000
- **最大变化**: +200.0000
- **总变化**: +1550.0000
- **正变化**: 60 条
- **负变化**: 25 条
- **无变化**: 15 条
```

---

## 常见错误处理

### 错误1：数据库文件不存在

**错误信息**：
```
错误: unable to open database file
```

**原因**：指定的 `--db` 路径不正确或文件不存在。

**解决方案**：
```bash
# 检查文件是否存在
ls -la ./data/mydb.db

# 使用绝对路径
python -m dataset_diff_reporter \
    --db /absolute/path/to/mydb.db \
    --old-table table1 \
    --new-table table2 \
    --pk id
```

### 错误2：表不存在

**错误信息**：
```
错误: no such table: table_name
```

**原因**：指定的表名在数据库中不存在。

**解决方案**：
```bash
# 检查数据库中的表
sqlite3 ./data/mydb.db ".tables"

# 检查表名拼写
python -m dataset_diff_reporter \
    --db ./data/mydb.db \
    --old-table correct_table_name \
    --new-table another_correct_name \
    --pk id
```

### 错误3：主键列不存在

**错误信息**：
```
错误: 主键列 id 不存在于数据集中
```

**原因**：指定的主键列在表中不存在。

**解决方案**：
```bash
# 检查表结构
sqlite3 ./data/mydb.db ".schema table_name"

# 使用正确的主键列名
python -m dataset_diff_reporter \
    --db ./data/mydb.db \
    --old-table table1 \
    --new-table table2 \
    --pk correct_primary_key
```

### 错误4：缺少必需参数

**错误信息**：
```
error: the following arguments are required: --db, --old-table, --new-table, --pk
```

**原因**：缺少必需的命令行参数。

**解决方案**：
```bash
# 查看帮助
python -m dataset_diff_reporter --help

# 确保提供所有必需参数
python -m dataset_diff_reporter \
    --db ./data/mydb.db \
    --old-table table1 \
    --new-table table2 \
    --pk id
```

### 错误5：权限不足

**错误信息**：
```
错误: permission denied
```

**原因**：
- 无法读取数据库文件
- 无法写入输出文件

**解决方案**：
```bash
# 检查文件权限
ls -la ./data/mydb.db
ls -la ./reports/

# 修改权限（如需要）
chmod 644 ./data/mydb.db
chmod 755 ./reports/
```

### 错误6：数据类型不匹配

**错误信息**：
```
错误: unsupported operand type(s) for -: 'str' and 'str'
```

**原因**：尝试对非数值类型进行数值统计。

**解决方案**：
- 这通常是警告信息，不影响报告生成
- 数值统计会自动跳过非数值列

### 错误7：内存不足

**错误信息**：
```
错误: MemoryError
```

**原因**：数据集过大，超出可用内存。

**解决方案**：
1. 分批处理数据
2. 使用更高效的主键索引
3. 增加系统可用内存

---

## API 接口

### DatasetDiffReporter 类

```python
from dataset_diff_reporter import DatasetDiffReporter

# 初始化
reporter = DatasetDiffReporter(primary_keys=['id'])
```

#### 方法列表

| 方法 | 说明 |
|------|------|
| `align_schema(df_old, df_new, fill_missing=None)` | 对齐两个数据集的 Schema |
| `find_changes(df_old, df_new, ignore_columns=None)` | 按主键找出增删改记录 |
| `calculate_numeric_changes(df_old, df_new, numeric_columns=None)` | 计算数值变化统计 |
| `generate_markdown_report(schema_info, changes, numeric_stats, report_title)` | 生成 Markdown 报告 |
| `compare_from_sqlite(db_path, table_name_old, table_name_new, ignore_columns=None)` | 从 SQLite 数据库进行完整对比 |
| `compare_from_dataframes(df_old, df_new, ignore_columns=None)` | 从 DataFrame 进行完整对比 |

#### compare_from_sqlite 返回值

```python
{
    'schema_info': {
        'columns_added': [],      # 新增列列表
        'columns_removed': [],    # 删除列列表
        'columns_common': [],     # 共同列列表
        'dtype_changes': []       # 类型变化列表
    },
    'changes': {
        'added': pd.DataFrame,    # 新增记录
        'removed': pd.DataFrame,  # 删除记录
        'modified': pd.DataFrame  # 修改记录（包含旧值和新值）
    },
    'numeric_stats': {
        'overall': {...},         # 整体统计
        'columns': {...}          # 各列详细统计
    },
    'report': str                 # Markdown 报告字符串
}
```

---

## 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行特定测试
python -m pytest tests/test_core.py -v
python -m pytest tests/test_cli.py -v

# 生成覆盖率报告
python -m pytest tests/ --cov=dataset_diff_reporter
```

---

## 许可证

MIT License

---

## 贡献

欢迎提交 Issue 和 Pull Request！
