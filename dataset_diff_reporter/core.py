import sqlite3
import pandas as pd
from typing import List, Dict, Any, Tuple, Optional


class DatasetDiffReporter:
    """数据集快照对比工具，支持schema对齐、按主键找增删改、数值变化统计和Markdown报告生成"""
    
    def __init__(self, primary_keys: List[str]):
        """
        初始化数据集对比工具
        
        Args:
            primary_keys: 主键列名列表，用于识别数据行
        """
        self.primary_keys = primary_keys
    
    def align_schema(
        self, 
        df_old: pd.DataFrame, 
        df_new: pd.DataFrame,
        fill_missing: Any = None
    ) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
        """
        对齐两个数据集的schema
        
        Args:
            df_old: 旧数据集
            df_new: 新数据集
            fill_missing: 缺失列的填充值
            
        Returns:
            对齐后的旧数据集、对齐后的新数据集、schema变化信息
        """
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
        
        # 对齐列
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
            df_old: 旧数据集
            df_new: 新数据集
            ignore_columns: 忽略比较的列名列表
            
        Returns:
            包含新增、删除、修改的数据字典
        """
        ignore_columns = ignore_columns or []
        
        # 确保主键存在
        for pk in self.primary_keys:
            if pk not in df_old.columns or pk not in df_new.columns:
                raise ValueError(f"主键列 {pk} 不存在于数据集中")
        
        # 创建主键的元组用于比较
        df_old['_pk_tuple'] = df_old[self.primary_keys].apply(tuple, axis=1)
        df_new['_pk_tuple'] = df_new[self.primary_keys].apply(tuple, axis=1)
        
        old_pks = set(df_old['_pk_tuple'])
        new_pks = set(df_new['_pk_tuple'])
        
        # 新增数据
        added_pks = new_pks - old_pks
        added_df = df_new[df_new['_pk_tuple'].isin(added_pks)].drop(columns=['_pk_tuple'])
        
        # 删除数据
        removed_pks = old_pks - new_pks
        removed_df = df_old[df_old['_pk_tuple'].isin(removed_pks)].drop(columns=['_pk_tuple'])
        
        # 找出共同主键的数据
        common_pks = old_pks & new_pks
        
        # 找出修改的数据
        compare_cols = [col for col in df_old.columns if col not in ignore_columns and col != '_pk_tuple']
        
        changes = []
        for pk_tuple in common_pks:
            # 使用 _pk_tuple 列来查找行，避免单主键/复合主键的索引问题
            old_rows = df_old[df_old['_pk_tuple'] == pk_tuple]
            new_rows = df_new[df_new['_pk_tuple'] == pk_tuple]
            
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
        
        # 清理临时列
        df_old.drop(columns=['_pk_tuple'], inplace=True)
        df_new.drop(columns=['_pk_tuple'], inplace=True)
        
        return {
            'added': added_df,
            'removed': removed_df,
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
            df_old: 旧数据集
            df_new: 新数据集
            numeric_columns: 指定要计算的数值列，如果为None则自动识别数值列
            
        Returns:
            数值变化统计信息
        """
        # 确保主键存在
        for pk in self.primary_keys:
            if pk not in df_old.columns or pk not in df_new.columns:
                raise ValueError(f"主键列 {pk} 不存在于数据集中")
        
        # 自动识别数值列
        if numeric_columns is None:
            numeric_columns = df_old.select_dtypes(include=['number']).columns.tolist()
            # 排除主键列
            numeric_columns = [col for col in numeric_columns if col not in self.primary_keys]
        
        # 找出共同主键的数据
        df_old = df_old.set_index(self.primary_keys)
        df_new = df_new.set_index(self.primary_keys)
        
        common_indices = df_old.index.intersection(df_new.index)
        
        # 只考虑共同存在的行
        old_common = df_old.loc[common_indices]
        new_common = df_new.loc[common_indices]
        
        stats = {
            'overall': {
                'total_rows_old': len(df_old),
                'total_rows_new': len(df_new),
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
                'mean_change': changes.mean(),
                'median_change': changes.median(),
                'min_change': changes.min(),
                'max_change': changes.max(),
                'sum_change': changes.sum(),
                'positive_changes': (changes > 0).sum(),
                'negative_changes': (changes < 0).sum(),
                'no_changes': (changes == 0).sum()
            }
            
            # 处理NaN
            col_stats['nan_count_old'] = old_vals.isna().sum()
            col_stats['nan_count_new'] = new_vals.isna().sum()
            
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
        """
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
        
        if schema_info['columns_added']:
            report.append("### 新增列")
            report.append("")
            for col in schema_info['columns_added']:
                report.append(f"- `{col}`")
            report.append("")
        
        if schema_info['columns_removed']:
            report.append("### 删除列")
            report.append("")
            for col in schema_info['columns_removed']:
                report.append(f"- `{col}`")
            report.append("")
        
        if schema_info['dtype_changes']:
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
        """
        conn = sqlite3.connect(db_path)
        
        # 读取数据
        df_old = pd.read_sql(f"SELECT * FROM {table_name_old}", conn)
        df_new = pd.read_sql(f"SELECT * FROM {table_name_new}", conn)
        
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
            df_old: 旧数据集
            df_new: 新数据集
            ignore_columns: 忽略比较的列名列表
            
        Returns:
            包含所有对比结果的字典
        """
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
