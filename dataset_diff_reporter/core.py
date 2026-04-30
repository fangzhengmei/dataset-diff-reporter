import sqlite3
import os
import re
import pandas as pd
from typing import List, Dict, Any, Tuple, Optional


class DatasetDiffError(Exception):
    """数据集对比工具的基础异常类"""
    pass


class InvalidInputError(DatasetDiffError, ValueError):
    """输入参数无效异常
    
    继承自 ValueError 以保持向后兼容性
    """
    pass


class SecurityError(DatasetDiffError, RuntimeError):
    """安全相关异常（如SQL注入风险）"""
    pass


class DataIntegrityError(DatasetDiffError, ValueError):
    """数据完整性异常（如重复主键）
    
    继承自 ValueError 以保持向后兼容性
    """
    pass


class DatabaseError(DatasetDiffError, RuntimeError):
    """数据库操作异常"""
    pass


class DatasetDiffReporter:
    """数据集快照对比工具，支持schema对齐、按主键找增删改、数值变化统计和Markdown报告生成"""
    
    # 合法的SQLite标识符模式（字母、数字、下划线，不以数字开头）
    _VALID_IDENTIFIER_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
    
    def __init__(self, primary_keys: List[str]):
        """
        初始化数据集对比工具
        
        Args:
            primary_keys: 主键列名列表，用于识别数据行
            
        Raises:
            InvalidInputError: 当主键列表无效时
        """
        self._validate_primary_keys(primary_keys)
        self.primary_keys = list(primary_keys)
    
    @staticmethod
    def _validate_primary_keys(primary_keys: List[str]) -> None:
        """
        验证主键列表的有效性
        
        Args:
            primary_keys: 主键列名列表
            
        Raises:
            InvalidInputError: 当主键列表无效时
        """
        if primary_keys is None:
            raise InvalidInputError("主键列表不能为 None")
        
        if not isinstance(primary_keys, (list, tuple)):
            raise InvalidInputError(
                f"主键列表必须是列表或元组类型，实际类型: {type(primary_keys).__name__}"
            )
        
        if len(primary_keys) == 0:
            raise InvalidInputError("主键列表不能为空，必须至少指定一个主键列")
        
        for i, pk in enumerate(primary_keys):
            if not isinstance(pk, str):
                raise InvalidInputError(
                    f"主键列名必须是字符串类型，第 {i+1} 个主键的类型: {type(pk).__name__}"
                )
            
            pk_stripped = pk.strip()
            if not pk_stripped:
                raise InvalidInputError(f"第 {i+1} 个主键列名不能为空或仅包含空白字符")
            
            if not DatasetDiffReporter._VALID_IDENTIFIER_PATTERN.match(pk_stripped):
                raise InvalidInputError(
                    f"主键列名 '{pk_stripped}' 格式不合法，"
                    "必须以字母或下划线开头，且只包含字母、数字和下划线"
                )
    
    @staticmethod
    def _validate_dataframe(df: Any, df_name: str) -> None:
        """
        验证DataFrame的有效性
        
        Args:
            df: 待验证的DataFrame
            df_name: DataFrame的名称（用于错误消息）
            
        Raises:
            InvalidInputError: 当DataFrame无效时
        """
        if df is None:
            raise InvalidInputError(f"{df_name} 不能为 None")
        
        if not isinstance(df, pd.DataFrame):
            raise InvalidInputError(
                f"{df_name} 必须是 pandas DataFrame 类型，实际类型: {type(df).__name__}"
            )
    
    @staticmethod
    def _validate_table_name(table_name: str, param_name: str) -> None:
        """
        验证表名的安全性（防止SQL注入）
        
        Args:
            table_name: 待验证的表名
            param_name: 参数名称（用于错误消息）
            
        Raises:
            SecurityError: 当表名包含潜在的SQL注入风险时
            InvalidInputError: 当表名格式不合法时
        """
        if table_name is None:
            raise InvalidInputError(f"{param_name} 不能为 None")
        
        if not isinstance(table_name, str):
            raise InvalidInputError(
                f"{param_name} 必须是字符串类型，实际类型: {type(table_name).__name__}"
            )
        
        table_name_stripped = table_name.strip()
        if not table_name_stripped:
            raise InvalidInputError(f"{param_name} 不能为空或仅包含空白字符")
        
        # 检查SQL注入风险
        # 禁止的字符：; -- ' " /* */ 等
        dangerous_chars = [';', '--', "'", '"', '/*', '*/', '\\', '\x00']
        for char in dangerous_chars:
            if char in table_name_stripped:
                raise SecurityError(
                    f"{param_name} '{table_name_stripped}' 包含危险字符，可能存在SQL注入风险。"
                    f"表名不能包含以下字符: {dangerous_chars}"
                )
        
        # 验证标识符格式
        if not DatasetDiffReporter._VALID_IDENTIFIER_PATTERN.match(table_name_stripped):
            raise InvalidInputError(
                f"{param_name} '{table_name_stripped}' 格式不合法，"
                "必须以字母或下划线开头，且只包含字母、数字和下划线"
            )
    
    @staticmethod
    def _validate_db_path(db_path: str) -> None:
        """
        验证数据库路径的安全性和有效性
        
        Args:
            db_path: 数据库文件路径
            
        Raises:
            InvalidInputError: 当路径无效时
            SecurityError: 当路径包含潜在安全风险时
        """
        if db_path is None:
            raise InvalidInputError("数据库路径不能为 None")
        
        if not isinstance(db_path, str):
            raise InvalidInputError(
                f"数据库路径必须是字符串类型，实际类型: {type(db_path).__name__}"
            )
        
        db_path_stripped = db_path.strip()
        if not db_path_stripped:
            raise InvalidInputError("数据库路径不能为空或仅包含空白字符")
        
        # 安全检查：防止路径遍历攻击
        # 禁止的模式：.. // 等
        if '..' in db_path_stripped:
            raise SecurityError(
                f"数据库路径 '{db_path_stripped}' 包含 '..'，可能存在路径遍历攻击风险"
            )
        
        # Windows 特有的安全检查
        if os.name == 'nt':
            # 检查是否包含 UNC 路径或其他危险模式
            if db_path_stripped.startswith('\\\\') or db_path_stripped.startswith('//'):
                raise SecurityError(
                    f"数据库路径 '{db_path_stripped}' 不支持 UNC 路径"
                )
    
    @staticmethod
    def _check_duplicate_primary_keys(df: pd.DataFrame, primary_keys: List[str], df_name: str) -> None:
        """
        检查DataFrame中是否存在重复主键
        
        Args:
            df: 待检查的DataFrame
            primary_keys: 主键列名列表
            df_name: DataFrame的名称（用于错误消息）
            
        Raises:
            DataIntegrityError: 当存在重复主键时
        """
        if len(df) == 0:
            return
        
        # 检查主键列是否存在
        for pk in primary_keys:
            if pk not in df.columns:
                raise InvalidInputError(
                    f"主键列 '{pk}' 不存在于 {df_name} 中。"
                    f"可用列: {list(df.columns)}"
                )
        
        # 检查重复主键
        pk_series = df[primary_keys].apply(tuple, axis=1)
        duplicates = pk_series.duplicated()
        
        if duplicates.any():
            duplicate_pks = pk_series[duplicates].unique().tolist()
            raise DataIntegrityError(
                f"{df_name} 中存在重复主键。"
                f"重复的主键值: {duplicate_pks[:5]}"
                f"{'... 还有更多' if len(duplicate_pks) > 5 else ''}"
            )
    
    @staticmethod
    def _validate_string_list(str_list: Any, param_name: str) -> List[str]:
        """
        验证字符串列表参数
        
        Args:
            str_list: 待验证的列表
            param_name: 参数名称（用于错误消息）
            
        Returns:
            验证后的列表
            
        Raises:
            InvalidInputError: 当列表无效时
        """
        if str_list is None:
            return []
        
        if not isinstance(str_list, (list, tuple)):
            raise InvalidInputError(
                f"{param_name} 必须是列表或元组类型，实际类型: {type(str_list).__name__}"
            )
        
        result = []
        for i, item in enumerate(str_list):
            if not isinstance(item, str):
                raise InvalidInputError(
                    f"{param_name} 中的元素必须是字符串类型，"
                    f"第 {i+1} 个元素的类型: {type(item).__name__}"
                )
            result.append(item.strip())
        
        return result
    
    def align_schema(
        self, 
        df_old: pd.DataFrame, 
        df_new: pd.DataFrame,
        fill_missing: Any = None
    ) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
        """
        对齐两个数据集的schema
        
        Args:
            df_old: 旧数据集（不会被修改）
            df_new: 新数据集（不会被修改）
            fill_missing: 缺失列的填充值
            
        Returns:
            对齐后的旧数据集、对齐后的新数据集、schema变化信息
            
        Raises:
            InvalidInputError: 当输入参数无效时
        """
        # 输入验证
        self._validate_dataframe(df_old, "旧数据集 (df_old)")
        self._validate_dataframe(df_new, "新数据集 (df_new)")
        
        schema_info = {
            'columns_added': [],
            'columns_removed': [],
            'columns_common': [],
            'dtype_changes': []
        }
        
        old_cols = set(df_old.columns)
        new_cols = set(df_new.columns)
        
        schema_info['columns_added'] = list(new_cols - old_cols)
        schema_info['columns_removed'] = list(old_cols - new_cols)
        schema_info['columns_common'] = list(old_cols & new_cols)
        
        # 检查类型变化
        for col in schema_info['columns_common']:
            old_dtype = str(df_old[col].dtype)
            new_dtype = str(df_new[col].dtype)
            if old_dtype != new_dtype:
                schema_info['dtype_changes'].append({
                    'column': col,
                    'old_dtype': old_dtype,
                    'new_dtype': new_dtype
                })
        
        # 对齐列 - 使用副本，不修改原始数据
        df_old_aligned = df_old.copy()
        df_new_aligned = df_new.copy()
        
        # 为旧数据集添加新列（缺失的列）
        for col in schema_info['columns_added']:
            df_old_aligned[col] = fill_missing
        
        # 为新数据集添加已删除的列（缺失的列）
        for col in schema_info['columns_removed']:
            df_new_aligned[col] = fill_missing
        
        # 确保列顺序一致
        all_cols = sorted(set(list(df_old_aligned.columns) + list(df_new_aligned.columns)))
        df_old_aligned = df_old_aligned[all_cols]
        df_new_aligned = df_new_aligned[all_cols]
        
        return df_old_aligned, df_new_aligned, schema_info
    
    def find_changes(
        self, 
        df_old: pd.DataFrame, 
        df_new: pd.DataFrame,
        ignore_columns: List[str] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        按主键找增删改
        
        Args:
            df_old: 旧数据集（不会被修改）
            df_new: 新数据集（不会被修改）
            ignore_columns: 忽略比较的列名列表
            
        Returns:
            包含新增、删除、修改的数据字典
            
        Raises:
            InvalidInputError: 当输入参数无效时
            DataIntegrityError: 当数据存在完整性问题时
        """
        # 输入验证
        self._validate_dataframe(df_old, "旧数据集 (df_old)")
        self._validate_dataframe(df_new, "新数据集 (df_new)")
        ignore_columns = self._validate_string_list(ignore_columns, "忽略列列表 (ignore_columns)")
        
        # 确保主键存在
        for pk in self.primary_keys:
            if pk not in df_old.columns:
                raise InvalidInputError(
                    f"主键列 '{pk}' 不存在于旧数据集中。"
                    f"旧数据集的列: {list(df_old.columns)}"
                )
            if pk not in df_new.columns:
                raise InvalidInputError(
                    f"主键列 '{pk}' 不存在于新数据集中。"
                    f"新数据集的列: {list(df_new.columns)}"
                )
        
        # 检查重复主键（在数据修改前检查）
        self._check_duplicate_primary_keys(df_old, self.primary_keys, "旧数据集 (df_old)")
        self._check_duplicate_primary_keys(df_new, self.primary_keys, "新数据集 (df_new)")
        
        # 使用副本操作，不修改原始数据
        df_old_copy = df_old.copy()
        df_new_copy = df_new.copy()
        
        # 创建主键的元组用于比较
        df_old_copy['_pk_tuple'] = df_old_copy[self.primary_keys].apply(tuple, axis=1)
        df_new_copy['_pk_tuple'] = df_new_copy[self.primary_keys].apply(tuple, axis=1)
        
        old_pks = set(df_old_copy['_pk_tuple'])
        new_pks = set(df_new_copy['_pk_tuple'])
        
        # 新增数据
        added_pks = new_pks - old_pks
        added_df = df_new_copy[df_new_copy['_pk_tuple'].isin(added_pks)].drop(columns=['_pk_tuple'])
        
        # 删除数据
        removed_pks = old_pks - new_pks
        removed_df = df_old_copy[df_old_copy['_pk_tuple'].isin(removed_pks)].drop(columns=['_pk_tuple'])
        
        # 找出共同主键的数据
        common_pks = old_pks & new_pks
        
        # 找出修改的数据
        compare_cols = [col for col in df_old_copy.columns if col not in ignore_columns and col != '_pk_tuple']
        
        changes = []
        for pk_tuple in common_pks:
            # 使用 _pk_tuple 列来查找行
            old_rows = df_old_copy[df_old_copy['_pk_tuple'] == pk_tuple]
            new_rows = df_new_copy[df_new_copy['_pk_tuple'] == pk_tuple]
            
            if len(old_rows) == 0 or len(new_rows) == 0:
                continue
            
            old_row = old_rows.iloc[0]
            new_row = new_rows.iloc[0]
            
            row_changed = False
            change_details = {}
            
            for col in compare_cols:
                old_val = old_row[col]
                new_val = new_row[col]
                
                # 处理NaN的比较
                if pd.isna(old_val) and pd.isna(new_val):
                    continue
                elif pd.isna(old_val) or pd.isna(new_val):
                    row_changed = True
                    change_details[f'{col}_old'] = old_val
                    change_details[f'{col}_new'] = new_val
                elif old_val != new_val:
                    row_changed = True
                    change_details[f'{col}_old'] = old_val
                    change_details[f'{col}_new'] = new_val
            
            if row_changed:
                # 构建结果行
                result_row = {}
                for i, pk in enumerate(self.primary_keys):
                    result_row[pk] = pk_tuple[i]
                result_row.update(change_details)
                changes.append(result_row)
        
        modified_df = pd.DataFrame(changes)
        
        return {
            'added': added_df.reset_index(drop=True),
            'removed': removed_df.reset_index(drop=True),
            'modified': modified_df
        }
    
    def calculate_numeric_changes(
        self, 
        df_old: pd.DataFrame, 
        df_new: pd.DataFrame,
        numeric_columns: List[str] = None
    ) -> Dict[str, Any]:
        """
        计算数值变化统计
        
        Args:
            df_old: 旧数据集（不会被修改）
            df_new: 新数据集（不会被修改）
            numeric_columns: 指定要计算的数值列，如果为None则自动识别数值列
            
        Returns:
            数值变化统计信息
            
        Raises:
            InvalidInputError: 当输入参数无效时
        """
        # 输入验证
        self._validate_dataframe(df_old, "旧数据集 (df_old)")
        self._validate_dataframe(df_new, "新数据集 (df_new)")
        numeric_columns = self._validate_string_list(numeric_columns, "数值列列表 (numeric_columns)")
        
        # 确保主键存在
        for pk in self.primary_keys:
            if pk not in df_old.columns:
                raise InvalidInputError(
                    f"主键列 '{pk}' 不存在于旧数据集中。"
                    f"旧数据集的列: {list(df_old.columns)}"
                )
            if pk not in df_new.columns:
                raise InvalidInputError(
                    f"主键列 '{pk}' 不存在于新数据集中。"
                    f"新数据集的列: {list(df_new.columns)}"
                )
        
        # 自动识别数值列
        if not numeric_columns:
            numeric_columns = df_old.select_dtypes(include=['number']).columns.tolist()
            # 排除主键列
            numeric_columns = [col for col in numeric_columns if col not in self.primary_keys]
        
        # 验证指定的数值列是否存在
        for col in numeric_columns:
            if col not in df_old.columns:
                raise InvalidInputError(
                    f"指定的数值列 '{col}' 不存在于旧数据集中。"
                    f"旧数据集的列: {list(df_old.columns)}"
                )
            if col not in df_new.columns:
                raise InvalidInputError(
                    f"指定的数值列 '{col}' 不存在于新数据集中。"
                    f"新数据集的列: {list(df_new.columns)}"
                )
        
        # 使用副本操作，不修改原始数据
        df_old_copy = df_old.copy()
        df_new_copy = df_new.copy()
        
        # 找出共同主键的数据
        df_old_copy = df_old_copy.set_index(self.primary_keys)
        df_new_copy = df_new_copy.set_index(self.primary_keys)
        
        common_indices = df_old_copy.index.intersection(df_new_copy.index)
        
        # 只考虑共同存在的行
        old_common = df_old_copy.loc[common_indices]
        new_common = df_new_copy.loc[common_indices]
        
        stats = {
            'overall': {
                'total_rows_old': len(df_old_copy),
                'total_rows_new': len(df_new_copy),
                'common_rows': len(common_indices)
            },
            'columns': {}
        }
        
        for col in numeric_columns:
            if col not in old_common.columns or col not in new_common.columns:
                continue
            
            old_vals = old_common[col]
            new_vals = new_common[col]
            
            # 计算变化
            changes = new_vals - old_vals
            
            # 统计信息
            col_stats = {
                'count': len(changes),
                'mean_change': float(changes.mean()) if len(changes) > 0 else 0.0,
                'median_change': float(changes.median()) if len(changes) > 0 else 0.0,
                'min_change': float(changes.min()) if len(changes) > 0 else 0.0,
                'max_change': float(changes.max()) if len(changes) > 0 else 0.0,
                'sum_change': float(changes.sum()) if len(changes) > 0 else 0.0,
                'positive_changes': int((changes > 0).sum()),
                'negative_changes': int((changes < 0).sum()),
                'no_changes': int((changes == 0).sum())
            }
            
            # 处理NaN
            col_stats['nan_count_old'] = int(old_vals.isna().sum())
            col_stats['nan_count_new'] = int(new_vals.isna().sum())
            
            stats['columns'][col] = col_stats
        
        return stats
    
    def generate_markdown_report(
        self,
        schema_info: Dict[str, Any],
        changes: Dict[str, pd.DataFrame],
        numeric_stats: Dict[str, Any],
        report_title: str = "数据集快照对比报告"
    ) -> str:
        """
        生成Markdown格式的对比报告
        
        Args:
            schema_info: schema变化信息
            changes: 数据变化信息（增删改）
            numeric_stats: 数值变化统计
            report_title: 报告标题
            
        Returns:
            Markdown格式的报告内容
            
        Raises:
            InvalidInputError: 当输入参数无效时
        """
        # 输入验证
        if schema_info is None:
            raise InvalidInputError("schema_info 不能为 None")
        if not isinstance(schema_info, dict):
            raise InvalidInputError(
                f"schema_info 必须是字典类型，实际类型: {type(schema_info).__name__}"
            )
        
        if changes is None:
            raise InvalidInputError("changes 不能为 None")
        if not isinstance(changes, dict):
            raise InvalidInputError(
                f"changes 必须是字典类型，实际类型: {type(changes).__name__}"
            )
        
        if numeric_stats is None:
            raise InvalidInputError("numeric_stats 不能为 None")
        if not isinstance(numeric_stats, dict):
            raise InvalidInputError(
                f"numeric_stats 必须是字典类型，实际类型: {type(numeric_stats).__name__}"
            )
        
        if report_title is None:
            report_title = "数据集快照对比报告"
        if not isinstance(report_title, str):
            raise InvalidInputError(
                f"report_title 必须是字符串类型，实际类型: {type(report_title).__name__}"
            )
        
        report = []
        
        # 标题
        report.append(f"# {report_title}")
        report.append("")
        
        # 摘要
        report.append("## 摘要")
        report.append("")
        
        added_count = len(changes.get('added', pd.DataFrame()))
        removed_count = len(changes.get('removed', pd.DataFrame()))
        modified_count = len(changes.get('modified', pd.DataFrame()))
        
        report.append(f"- **新增记录**: {added_count} 条")
        report.append(f"- **删除记录**: {removed_count} 条")
        report.append(f"- **修改记录**: {modified_count} 条")
        report.append("")
        
        # Schema变化
        report.append("## Schema变化")
        report.append("")
        
        if schema_info.get('columns_added'):
            report.append("### 新增列")
            report.append("")
            for col in schema_info['columns_added']:
                report.append(f"- `{col}`")
            report.append("")
        
        if schema_info.get('columns_removed'):
            report.append("### 删除列")
            report.append("")
            for col in schema_info['columns_removed']:
                report.append(f"- `{col}`")
            report.append("")
        
        if schema_info.get('dtype_changes'):
            report.append("### 类型变化")
            report.append("")
            for change in schema_info['dtype_changes']:
                report.append(f"- `{change['column']}`: `{change['old_dtype']}` → `{change['new_dtype']}`")
            report.append("")
        
        # 数据变化详情
        report.append("## 数据变化详情")
        report.append("")
        
        # 新增记录
        if added_count > 0:
            report.append("### 新增记录")
            report.append("")
            added_df = changes['added']
            report.append("```")
            report.append(added_df.to_string(index=False))
            report.append("```")
            report.append("")
        
        # 删除记录
        if removed_count > 0:
            report.append("### 删除记录")
            report.append("")
            removed_df = changes['removed']
            report.append("```")
            report.append(removed_df.to_string(index=False))
            report.append("```")
            report.append("")
        
        # 修改记录
        if modified_count > 0:
            report.append("### 修改记录")
            report.append("")
            modified_df = changes['modified']
            report.append("```")
            report.append(modified_df.to_string(index=False))
            report.append("```")
            report.append("")
        
        # 数值变化统计
        if numeric_stats.get('columns'):
            report.append("## 数值变化统计")
            report.append("")
            
            for col, stats in numeric_stats['columns'].items():
                report.append(f"### 列: `{col}`")
                report.append("")
                report.append(f"- **总行数**: {stats['count']}")
                report.append(f"- **平均变化**: {stats['mean_change']:.4f}")
                report.append(f"- **中位数变化**: {stats['median_change']:.4f}")
                report.append(f"- **最小变化**: {stats['min_change']:.4f}")
                report.append(f"- **最大变化**: {stats['max_change']:.4f}")
                report.append(f"- **总变化**: {stats['sum_change']:.4f}")
                report.append(f"- **正变化**: {stats['positive_changes']} 条")
                report.append(f"- **负变化**: {stats['negative_changes']} 条")
                report.append(f"- **无变化**: {stats['no_changes']} 条")
                report.append("")
        
        return "\n".join(report)
    
    def compare_from_sqlite(
        self,
        db_path: str,
        table_name_old: str,
        table_name_new: str,
        ignore_columns: List[str] = None
    ) -> Dict[str, Any]:
        """
        从SQLite数据库读取两个表并进行对比
        
        Args:
            db_path: SQLite数据库文件路径
            table_name_old: 旧表名
            table_name_new: 新表名
            ignore_columns: 忽略比较的列名列表
            
        Returns:
            包含所有对比结果的字典
            
        Raises:
            InvalidInputError: 当输入参数无效时
            SecurityError: 当检测到安全风险时
            DatabaseError: 当数据库操作失败时
        """
        # 输入验证
        self._validate_db_path(db_path)
        self._validate_table_name(table_name_old, "旧表名 (table_name_old)")
        self._validate_table_name(table_name_new, "新表名 (table_name_new)")
        ignore_columns = self._validate_string_list(ignore_columns, "忽略列列表 (ignore_columns)")
        
        # 检查文件是否存在
        if not os.path.exists(db_path):
            raise InvalidInputError(
                f"数据库文件不存在: {db_path}\n"
                f"当前工作目录: {os.getcwd()}"
            )
        
        # 检查是否是文件
        if not os.path.isfile(db_path):
            raise InvalidInputError(f"指定的路径不是文件: {db_path}")
        
        conn = None
        try:
            # 连接数据库
            conn = sqlite3.connect(db_path)
            
            # 检查表是否存在
            cursor = conn.cursor()
            
            # 检查旧表
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name_old,)
            )
            if not cursor.fetchone():
                # 获取所有表名帮助用户诊断
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                all_tables = [row[0] for row in cursor.fetchall()]
                raise InvalidInputError(
                    f"旧表 '{table_name_old}' 不存在于数据库中。\n"
                    f"数据库中的表: {all_tables}"
                )
            
            # 检查新表
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name_new,)
            )
            if not cursor.fetchone():
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                all_tables = [row[0] for row in cursor.fetchall()]
                raise InvalidInputError(
                    f"新表 '{table_name_new}' 不存在于数据库中。\n"
                    f"数据库中的表: {all_tables}"
                )
            
            # 使用参数化查询读取数据（防止SQL注入）
            df_old = pd.read_sql(f"SELECT * FROM `{table_name_old}`", conn)
            df_new = pd.read_sql(f"SELECT * FROM `{table_name_new}`", conn)
            
        except sqlite3.Error as e:
            raise DatabaseError(
                f"数据库操作失败: {str(e)}\n"
                f"数据库路径: {db_path}\n"
                f"旧表名: {table_name_old}\n"
                f"新表名: {table_name_new}"
            ) from e
        finally:
            if conn:
                conn.close()
        
        # 对齐schema
        df_old_aligned, df_new_aligned, schema_info = self.align_schema(df_old, df_new)
        
        # 找增删改
        changes = self.find_changes(df_old_aligned, df_new_aligned, ignore_columns)
        
        # 数值变化统计
        numeric_stats = self.calculate_numeric_changes(df_old_aligned, df_new_aligned)
        
        # 生成报告
        report = self.generate_markdown_report(schema_info, changes, numeric_stats)
        
        return {
            'schema_info': schema_info,
            'changes': changes,
            'numeric_stats': numeric_stats,
            'report': report
        }
    
    def compare_from_dataframes(
        self,
        df_old: pd.DataFrame,
        df_new: pd.DataFrame,
        ignore_columns: List[str] = None
    ) -> Dict[str, Any]:
        """
        从两个DataFrame进行对比
        
        Args:
            df_old: 旧数据集（不会被修改）
            df_new: 新数据集（不会被修改）
            ignore_columns: 忽略比较的列名列表
            
        Returns:
            包含所有对比结果的字典
            
        Raises:
            InvalidInputError: 当输入参数无效时
            DataIntegrityError: 当数据存在完整性问题时
        """
        # 输入验证（在各个方法内部进行）
        
        # 对齐schema
        df_old_aligned, df_new_aligned, schema_info = self.align_schema(df_old, df_new)
        
        # 找增删改
        changes = self.find_changes(df_old_aligned, df_new_aligned, ignore_columns)
        
        # 数值变化统计
        numeric_stats = self.calculate_numeric_changes(df_old_aligned, df_new_aligned)
        
        # 生成报告
        report = self.generate_markdown_report(schema_info, changes, numeric_stats)
        
        return {
            'schema_info': schema_info,
            'changes': changes,
            'numeric_stats': numeric_stats,
            'report': report
        }
