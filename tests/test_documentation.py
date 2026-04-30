"""
测试文档中描述的功能和使用场景
确保文档中的示例和说明与实际代码行为一致
"""
import pytest
import pandas as pd
import sqlite3
import os
import tempfile
from dataset_diff_reporter import DatasetDiffReporter


@pytest.fixture
def test_db_with_schema_changes():
    """创建包含Schema变化的测试数据库"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
        db_path = f.name
    
    conn = sqlite3.connect(db_path)
    
    # 旧表
    df_old = pd.DataFrame({
        'id': [1, 2, 3],
        'name': ['Alice', 'Bob', 'Charlie'],
        'age': [25, 30, 35],
        'old_column': ['a', 'b', 'c']  # 这个列会被删除
    })
    
    # 新表（包含Schema变化）
    df_new = pd.DataFrame({
        'id': [1, 2, 3],
        'name': ['Alice', 'Bob', 'Charles'],
        'age': [25, 31, 35],
        'new_column': ['x', 'y', 'z']  # 新增列
    })
    
    df_old.to_sql('table_old', conn, index=False, if_exists='replace')
    df_new.to_sql('table_new', conn, index=False, if_exists='replace')
    
    conn.close()
    
    yield db_path
    
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def test_db_numeric_only():
    """创建只包含数值变化的测试数据库"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
        db_path = f.name
    
    conn = sqlite3.connect(db_path)
    
    # 旧表
    df_old = pd.DataFrame({
        'id': [1, 2, 3, 4, 5],
        'value1': [100, 200, 300, 400, 500],
        'value2': [10.5, 20.5, 30.5, 40.5, 50.5]
    })
    
    # 新表（数值变化）
    df_new = pd.DataFrame({
        'id': [1, 2, 3, 4, 5],
        'value1': [150, 180, 300, 450, 450],  # +50, -20, 0, +50, -50
        'value2': [10.5, 25.5, 35.5, 40.5, 45.5]  # 0, +5, +5, 0, -5
    })
    
    df_old.to_sql('table_old', conn, index=False, if_exists='replace')
    df_new.to_sql('table_new', conn, index=False, if_exists='replace')
    
    conn.close()
    
    yield db_path
    
    if os.path.exists(db_path):
        os.unlink(db_path)


class TestReportStructure:
    """测试报告结构是否符合文档描述"""
    
    def test_report_contains_all_sections(self, test_db_with_schema_changes):
        """测试报告包含所有必需的章节"""
        reporter = DatasetDiffReporter(primary_keys=['id'])
        result = reporter.compare_from_sqlite(
            db_path=test_db_with_schema_changes,
            table_name_old='table_old',
            table_name_new='table_new'
        )
        
        report = result['report']
        
        # 检查报告结构
        assert "# 数据集快照对比报告" in report
        assert "## 摘要" in report
        assert "## Schema变化" in report
        assert "## 数据变化详情" in report
        assert "## 数值变化统计" in report
    
    def test_report_summary_section(self, test_db_with_schema_changes):
        """测试报告摘要部分"""
        reporter = DatasetDiffReporter(primary_keys=['id'])
        result = reporter.compare_from_sqlite(
            db_path=test_db_with_schema_changes,
            table_name_old='table_old',
            table_name_new='table_new'
        )
        
        report = result['report']
        
        # 检查摘要格式
        assert "新增记录" in report
        assert "删除记录" in report
        assert "修改记录" in report
        assert "条" in report  # 每个统计都有"条"
    
    def test_report_schema_changes_section(self, test_db_with_schema_changes):
        """测试报告Schema变化部分"""
        reporter = DatasetDiffReporter(primary_keys=['id'])
        result = reporter.compare_from_sqlite(
            db_path=test_db_with_schema_changes,
            table_name_old='table_old',
            table_name_new='table_new'
        )
        
        report = result['report']
        schema_info = result['schema_info']
        
        # 检查Schema变化
        if schema_info['columns_added']:
            assert "### 新增列" in report
            for col in schema_info['columns_added']:
                assert f"`{col}`" in report
        
        if schema_info['columns_removed']:
            assert "### 删除列" in report
            for col in schema_info['columns_removed']:
                assert f"`{col}`" in report
        
        if schema_info['dtype_changes']:
            assert "### 类型变化" in report
    
    def test_report_data_changes_section(self, test_db_with_schema_changes):
        """测试报告数据变化详情部分"""
        reporter = DatasetDiffReporter(primary_keys=['id'])
        result = reporter.compare_from_sqlite(
            db_path=test_db_with_schema_changes,
            table_name_old='table_old',
            table_name_new='table_new'
        )
        
        report = result['report']
        changes = result['changes']
        
        # 检查数据变化详情
        if len(changes['added']) > 0:
            assert "### 新增记录" in report
        
        if len(changes['removed']) > 0:
            assert "### 删除记录" in report
        
        if len(changes['modified']) > 0:
            assert "### 修改记录" in report
        
        # 检查代码块格式
        assert "```" in report  # 数据使用代码块展示
    
    def test_report_numeric_statistics_section(self, test_db_numeric_only):
        """测试报告数值变化统计部分"""
        reporter = DatasetDiffReporter(primary_keys=['id'])
        result = reporter.compare_from_sqlite(
            db_path=test_db_numeric_only,
            table_name_old='table_old',
            table_name_new='table_new'
        )
        
        report = result['report']
        numeric_stats = result['numeric_stats']
        
        # 检查数值统计部分
        assert "## 数值变化统计" in report
        
        # 检查每个数值列的统计
        for col in numeric_stats['columns'].keys():
            assert f"### 列: `{col}`" in report
            assert "总行数" in report
            assert "平均变化" in report
            assert "中位数变化" in report
            assert "最小变化" in report
            assert "最大变化" in report
            assert "总变化" in report
            assert "正变化" in report
            assert "负变化" in report
            assert "无变化" in report


class TestAPIDocumentation:
    """测试API文档中描述的功能"""
    
    def test_compare_from_dataframes_api(self):
        """测试compare_from_dataframes API"""
        df_old = pd.DataFrame({
            'id': [1, 2, 3],
            'name': ['Alice', 'Bob', 'Charlie'],
            'age': [25, 30, 35]
        })
        
        df_new = pd.DataFrame({
            'id': [1, 2, 4],
            'name': ['Alice', 'Bob', 'David'],
            'age': [25, 31, 28]
        })
        
        reporter = DatasetDiffReporter(primary_keys=['id'])
        result = reporter.compare_from_dataframes(df_old, df_new)
        
        # 检查返回值结构（符合文档描述）
        assert 'schema_info' in result
        assert 'changes' in result
        assert 'numeric_stats' in result
        assert 'report' in result
        
        # 检查changes结构
        assert 'added' in result['changes']
        assert 'removed' in result['changes']
        assert 'modified' in result['changes']
        
        # 检查schema_info结构
        assert 'columns_added' in result['schema_info']
        assert 'columns_removed' in result['schema_info']
        assert 'columns_common' in result['schema_info']
        assert 'dtype_changes' in result['schema_info']
        
        # 检查numeric_stats结构
        assert 'overall' in result['numeric_stats']
        assert 'columns' in result['numeric_stats']
    
    def test_individual_methods_api(self):
        """测试各个方法的API"""
        df_old = pd.DataFrame({
            'id': [1, 2],
            'name': ['Alice', 'Bob'],
            'age': [25, 30]
        })
        
        df_new = pd.DataFrame({
            'id': [1, 2],
            'name': ['Alice', 'Robert'],
            'age': [25, 31],
            'salary': [50000, 60000]  # 新增列
        })
        
        reporter = DatasetDiffReporter(primary_keys=['id'])
        
        # 测试align_schema
        df_old_aligned, df_new_aligned, schema_info = reporter.align_schema(df_old, df_new)
        assert 'salary' in schema_info['columns_added']
        assert set(df_old_aligned.columns) == set(df_new_aligned.columns)
        
        # 测试find_changes
        changes = reporter.find_changes(df_old_aligned, df_new_aligned)
        # id=1: salary 从 None 变为 50000（被认为是修改）
        # id=2: name 从 Bob 变为 Robert，age 从 30 变为 31，salary 从 None 变为 60000
        assert len(changes['modified']) == 2
        
        # 测试calculate_numeric_changes
        numeric_stats = reporter.calculate_numeric_changes(df_old_aligned, df_new_aligned)
        assert 'age' in numeric_stats['columns']
        
        # 测试generate_markdown_report
        report = reporter.generate_markdown_report(schema_info, changes, numeric_stats)
        assert isinstance(report, str)
        assert len(report) > 0


class TestDocumentationExamples:
    """测试文档中的示例代码"""
    
    def test_documentation_example_basic(self):
        """测试文档中的基本示例"""
        # 模拟文档中的示例数据
        df_old = pd.DataFrame({
            'id': [1, 2, 3],
            'name': ['ProductA', 'ProductB', 'ProductC'],
            'price': [100, 50, 200]
        })
        
        df_new = pd.DataFrame({
            'id': [1, 2, 4],
            'name': ['ProductA', 'ProductB_Updated', 'ProductD'],
            'price': [120, 50, 75]
        })
        
        reporter = DatasetDiffReporter(primary_keys=['id'])
        result = reporter.compare_from_dataframes(df_old, df_new)
        
        # 验证结果
        changes = result['changes']
        
        # 新增: id=4 (ProductD)
        assert len(changes['added']) == 1
        assert changes['added']['id'].values[0] == 4
        
        # 删除: id=3 (ProductC)
        assert len(changes['removed']) == 1
        assert changes['removed']['id'].values[0] == 3
        
        # 修改: 
        # - id=1: price 从 100 变为 120
        # - id=2: name 从 ProductB 变为 ProductB_Updated
        assert len(changes['modified']) == 2
        
        # 检查 id=1 的修改
        modified_1 = changes['modified'][changes['modified']['id'] == 1].iloc[0]
        assert modified_1['price_old'] == 100
        assert modified_1['price_new'] == 120
        
        # 检查 id=2 的修改
        modified_2 = changes['modified'][changes['modified']['id'] == 2].iloc[0]
        assert modified_2['name_old'] == 'ProductB'
        assert modified_2['name_new'] == 'ProductB_Updated'
        
        # 报告生成
        assert len(result['report']) > 0
    
    def test_documentation_example_composite_key(self):
        """测试文档中的复合主键示例"""
        # 模拟文档中的复合主键示例
        df_old = pd.DataFrame({
            'department_id': [1, 1, 2, 2],
            'employee_id': [1, 2, 1, 2],
            'name': ['Alice', 'Bob', 'Charlie', 'David'],
            'salary': [50000, 60000, 55000, 65000]
        })
        
        df_new = pd.DataFrame({
            'department_id': [1, 1, 2, 3],
            'employee_id': [1, 3, 1, 1],
            'name': ['Alice', 'Eve', 'Charlie', 'Frank'],
            'salary': [52000, 70000, 55000, 80000]
        })
        
        reporter = DatasetDiffReporter(primary_keys=['department_id', 'employee_id'])
        result = reporter.compare_from_dataframes(df_old, df_new)
        
        changes = result['changes']
        
        # 新增: (1,3), (3,1)
        assert len(changes['added']) == 2
        
        # 删除: (1,2), (2,2)
        assert len(changes['removed']) == 2
        
        # 修改: (1,1) - salary 50000→52000
        assert len(changes['modified']) == 1
        
        # 验证复合主键在修改记录中
        modified = changes['modified'].iloc[0]
        assert modified['department_id'] == 1
        assert modified['employee_id'] == 1
        assert modified['salary_old'] == 50000
        assert modified['salary_new'] == 52000


class TestIgnoreColumnsFeature:
    """测试忽略列功能（文档中描述的）"""
    
    def test_ignore_columns_in_comparison(self):
        """测试忽略列的比较"""
        df_old = pd.DataFrame({
            'id': [1, 2],
            'name': ['Alice', 'Bob'],
            'price': [100, 200],
            'updated_at': ['2023-01-01', '2023-01-01']
        })
        
        df_new = pd.DataFrame({
            'id': [1, 2],
            'name': ['Alice', 'Bob'],
            'price': [150, 200],
            'updated_at': ['2024-01-01', '2024-01-01']  # 这个列会变化
        })
        
        # 不忽略列
        reporter = DatasetDiffReporter(primary_keys=['id'])
        result_without_ignore = reporter.compare_from_dataframes(df_old, df_new)
        
        # 不忽略时，updated_at的变化会被检测到
        modified_without = result_without_ignore['changes']['modified']
        assert len(modified_without) == 2  # id=1 (price和updated_at), id=2 (updated_at)
        
        # 忽略updated_at列
        result_with_ignore = reporter.compare_from_dataframes(
            df_old, df_new, ignore_columns=['updated_at']
        )
        
        # 忽略后，只有price的变化会被检测到
        modified_with = result_with_ignore['changes']['modified']
        assert len(modified_with) == 1  # 只有id=1的price变化
        
        # 验证被忽略的列不在修改记录中
        modified_row = modified_with.iloc[0]
        assert 'updated_at_old' not in modified_row.index
        assert 'price_old' in modified_row.index
