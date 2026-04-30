import pytest
import pandas as pd
import sqlite3
import os
import tempfile
from dataset_diff_reporter import DatasetDiffReporter


@pytest.fixture
def sample_data():
    """创建测试用的样本数据"""
    # 旧数据
    df_old = pd.DataFrame({
        'id': [1, 2, 3, 4],
        'name': ['Alice', 'Bob', 'Charlie', 'David'],
        'age': [25, 30, 35, 40],
        'salary': [50000, 60000, 70000, 80000]
    })
    
    # 新数据（包含增删改）
    df_new = pd.DataFrame({
        'id': [1, 2, 3, 5],  # 删除了id=4，新增了id=5
        'name': ['Alice', 'Bob', 'Charles', 'Eve'],  # Charlie改名为Charles
        'age': [25, 31, 35, 28],  # Bob的年龄从30改为31
        'salary': [52000, 60000, 75000, 45000]  # Alice和Charlie的工资变了
    })
    
    return df_old, df_new


@pytest.fixture
def reporter():
    """创建DatasetDiffReporter实例"""
    return DatasetDiffReporter(primary_keys=['id'])


class TestSchemaAlignment:
    """测试schema对齐功能"""
    
    def test_schema_alignment_basic(self, reporter):
        """测试基本的schema对齐"""
        df_old = pd.DataFrame({
            'id': [1, 2],
            'name': ['Alice', 'Bob'],
            'age': [25, 30]
        })
        
        df_new = pd.DataFrame({
            'id': [1, 2],
            'name': ['Alice', 'Bob'],
            'salary': [50000, 60000]  # 新增列，删除了age列
        })
        
        df_old_aligned, df_new_aligned, schema_info = reporter.align_schema(df_old, df_new)
        
        # 检查schema信息
        assert 'age' in schema_info['columns_removed']
        assert 'salary' in schema_info['columns_added']
        assert 'id' in schema_info['columns_common']
        assert 'name' in schema_info['columns_common']
        
        # 检查对齐后的DataFrame
        assert set(df_old_aligned.columns) == {'id', 'name', 'age', 'salary'}
        assert set(df_new_aligned.columns) == {'id', 'name', 'age', 'salary'}
        
        # 检查缺失值填充
        assert df_old_aligned['salary'].isna().all()
        assert df_new_aligned['age'].isna().all()
    
    def test_schema_alignment_with_custom_fill(self, reporter):
        """测试使用自定义填充值的schema对齐"""
        df_old = pd.DataFrame({
            'id': [1, 2],
            'name': ['Alice', 'Bob']
        })
        
        df_new = pd.DataFrame({
            'id': [1, 2],
            'name': ['Alice', 'Bob'],
            'age': [25, 30]
        })
        
        df_old_aligned, df_new_aligned, schema_info = reporter.align_schema(
            df_old, df_new, fill_missing=0
        )
        
        # 检查自定义填充值
        assert (df_old_aligned['age'] == 0).all()
    
    def test_schema_alignment_dtype_changes(self, reporter):
        """测试检测类型变化"""
        df_old = pd.DataFrame({
            'id': [1, 2],
            'age': [25, 30]  # int类型
        })
        
        df_new = pd.DataFrame({
            'id': [1, 2],
            'age': ['25', '30']  # object类型
        })
        
        _, _, schema_info = reporter.align_schema(df_old, df_new)
        
        # 检查类型变化
        assert len(schema_info['dtype_changes']) == 1
        assert schema_info['dtype_changes'][0]['column'] == 'age'


class TestFindChanges:
    """测试按主键找增删改功能"""
    
    def test_find_added_records(self, reporter, sample_data):
        """测试找出新增记录"""
        df_old, df_new = sample_data
        
        changes = reporter.find_changes(df_old, df_new)
        
        # 检查新增记录
        assert len(changes['added']) == 1
        assert changes['added']['id'].values[0] == 5
        assert changes['added']['name'].values[0] == 'Eve'
    
    def test_find_removed_records(self, reporter, sample_data):
        """测试找出删除记录"""
        df_old, df_new = sample_data
        
        changes = reporter.find_changes(df_old, df_new)
        
        # 检查删除记录
        assert len(changes['removed']) == 1
        assert changes['removed']['id'].values[0] == 4
        assert changes['removed']['name'].values[0] == 'David'
    
    def test_find_modified_records(self, reporter, sample_data):
        """测试找出修改记录"""
        df_old, df_new = sample_data
        
        changes = reporter.find_changes(df_old, df_new)
        
        # 检查修改记录
        # id=2: age从30改为31
        # id=3: name从Charlie改为Charles，salary从70000改为75000
        # id=1: salary从50000改为52000
        assert len(changes['modified']) == 3
        
        # 检查id=1的修改
        modified_1 = changes['modified'][changes['modified']['id'] == 1].iloc[0]
        assert modified_1['salary_old'] == 50000
        assert modified_1['salary_new'] == 52000
        
        # 检查id=2的修改
        modified_2 = changes['modified'][changes['modified']['id'] == 2].iloc[0]
        assert modified_2['age_old'] == 30
        assert modified_2['age_new'] == 31
        
        # 检查id=3的修改
        modified_3 = changes['modified'][changes['modified']['id'] == 3].iloc[0]
        assert modified_3['name_old'] == 'Charlie'
        assert modified_3['name_new'] == 'Charles'
        assert modified_3['salary_old'] == 70000
        assert modified_3['salary_new'] == 75000
    
    def test_find_changes_with_ignore_columns(self, reporter, sample_data):
        """测试忽略某些列的比较"""
        df_old, df_new = sample_data
        
        # 忽略salary列
        changes = reporter.find_changes(df_old, df_new, ignore_columns=['salary'])
        
        # 检查修改记录（id=1的修改只涉及salary，应该被忽略）
        modified_ids = changes['modified']['id'].tolist()
        assert 1 not in modified_ids  # id=1的修改被忽略
        assert 2 in modified_ids  # id=2的age修改保留
        assert 3 in modified_ids  # id=3的name修改保留
    
    def test_find_changes_with_composite_primary_key(self, sample_data):
        """测试复合主键的情况"""
        # 创建使用复合主键的测试数据
        df_old = pd.DataFrame({
            'department': ['IT', 'IT', 'HR', 'HR'],
            'employee_id': [1, 2, 1, 2],
            'name': ['Alice', 'Bob', 'Charlie', 'David'],
            'salary': [50000, 60000, 55000, 65000]
        })
        
        df_new = pd.DataFrame({
            'department': ['IT', 'IT', 'HR', 'Finance'],
            'employee_id': [1, 3, 1, 1],
            'name': ['Alice', 'Eve', 'Charlie', 'Frank'],
            'salary': [52000, 70000, 55000, 80000]
        })
        
        reporter = DatasetDiffReporter(primary_keys=['department', 'employee_id'])
        changes = reporter.find_changes(df_old, df_new)
        
        # 检查新增记录
        assert len(changes['added']) == 2
        added_pks = [(row['department'], row['employee_id']) for _, row in changes['added'].iterrows()]
        assert ('IT', 3) in added_pks
        assert ('Finance', 1) in added_pks
        
        # 检查删除记录
        assert len(changes['removed']) == 2
        removed_pks = [(row['department'], row['employee_id']) for _, row in changes['removed'].iterrows()]
        assert ('IT', 2) in removed_pks
        assert ('HR', 2) in removed_pks
        
        # 检查修改记录
        assert len(changes['modified']) == 1
        assert changes['modified']['department'].values[0] == 'IT'
        assert changes['modified']['employee_id'].values[0] == 1
        assert changes['modified']['salary_old'].values[0] == 50000
        assert changes['modified']['salary_new'].values[0] == 52000


class TestNumericChanges:
    """测试数值变化统计功能"""
    
    def test_numeric_changes_basic(self, reporter, sample_data):
        """测试基本的数值变化统计"""
        df_old, df_new = sample_data
        
        stats = reporter.calculate_numeric_changes(df_old, df_new)
        
        # 检查整体统计
        assert stats['overall']['total_rows_old'] == 4
        assert stats['overall']['total_rows_new'] == 4
        assert stats['overall']['common_rows'] == 3  # id=1,2,3
        
        # 检查age列统计
        age_stats = stats['columns']['age']
        assert age_stats['count'] == 3
        assert age_stats['sum_change'] == 1  # 只有id=2的age变了(30→31)
        
        # 检查salary列统计
        salary_stats = stats['columns']['salary']
        assert salary_stats['count'] == 3
        # id=1: 50000→52000 (+2000)
        # id=2: 60000→60000 (0)
        # id=3: 70000→75000 (+5000)
        assert salary_stats['sum_change'] == 7000
        assert salary_stats['positive_changes'] == 2
        assert salary_stats['no_changes'] == 1
    
    def test_numeric_changes_with_specific_columns(self, reporter, sample_data):
        """测试指定数值列进行统计"""
        df_old, df_new = sample_data
        
        # 只统计salary列
        stats = reporter.calculate_numeric_changes(df_old, df_new, numeric_columns=['salary'])
        
        # 检查只统计了salary列
        assert 'salary' in stats['columns']
        assert 'age' not in stats['columns']


class TestMarkdownReport:
    """测试Markdown报告生成功能"""
    
    def test_generate_markdown_report(self, reporter, sample_data):
        """测试生成Markdown报告"""
        df_old, df_new = sample_data
        
        # 进行完整的对比
        result = reporter.compare_from_dataframes(df_old, df_new)
        
        # 检查报告生成
        report = result['report']
        
        # 检查报告包含关键信息
        assert "数据集快照对比报告" in report
        assert "新增记录" in report
        assert "1 条" in report
        assert "删除记录" in report
        assert "修改记录" in report
        assert "3 条" in report
        
        # 检查包含schema变化部分
        assert "Schema变化" in report
        
        # 检查包含数据变化详情
        assert "数据变化详情" in report
        assert "新增记录" in report
        assert "删除记录" in report
        assert "修改记录" in report
        
        # 检查包含数值变化统计
        assert "数值变化统计" in report
        assert "age" in report
        assert "salary" in report


class TestSQLiteIntegration:
    """测试SQLite集成功能"""
    
    def test_compare_from_sqlite(self, reporter, sample_data):
        """测试从SQLite数据库进行对比"""
        df_old, df_new = sample_data
        
        # 创建临时SQLite数据库
        with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            # 连接数据库并创建表
            conn = sqlite3.connect(db_path)
            df_old.to_sql('table_old', conn, index=False, if_exists='replace')
            df_new.to_sql('table_new', conn, index=False, if_exists='replace')
            conn.close()
            
            # 从数据库进行对比
            result = reporter.compare_from_sqlite(
                db_path=db_path,
                table_name_old='table_old',
                table_name_new='table_new'
            )
            
            # 检查结果
            assert 'schema_info' in result
            assert 'changes' in result
            assert 'numeric_stats' in result
            assert 'report' in result
            
            # 检查增删改数量
            assert len(result['changes']['added']) == 1
            assert len(result['changes']['removed']) == 1
            assert len(result['changes']['modified']) == 3
            
        finally:
            # 清理临时文件
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestCompareFromDataframes:
    """测试从DataFrame进行完整对比"""
    
    def test_compare_from_dataframes_full(self, reporter, sample_data):
        """测试完整的DataFrame对比流程"""
        df_old, df_new = sample_data
        
        result = reporter.compare_from_dataframes(df_old, df_new)
        
        # 检查所有结果都存在
        assert 'schema_info' in result
        assert 'changes' in result
        assert 'numeric_stats' in result
        assert 'report' in result
        
        # 检查增删改
        changes = result['changes']
        assert len(changes['added']) == 1
        assert len(changes['removed']) == 1
        assert len(changes['modified']) == 3
        
        # 检查报告生成
        assert len(result['report']) > 0


class TestEdgeCases:
    """测试边界情况"""
    
    def test_empty_dataframes(self, reporter):
        """测试空DataFrame的情况"""
        df_old = pd.DataFrame(columns=['id', 'name', 'age'])
        df_new = pd.DataFrame(columns=['id', 'name', 'age'])
        
        result = reporter.compare_from_dataframes(df_old, df_new)
        
        assert len(result['changes']['added']) == 0
        assert len(result['changes']['removed']) == 0
        assert len(result['changes']['modified']) == 0
    
    def test_no_changes(self, reporter):
        """测试没有任何变化的情况"""
        df = pd.DataFrame({
            'id': [1, 2, 3],
            'name': ['Alice', 'Bob', 'Charlie'],
            'age': [25, 30, 35]
        })
        
        result = reporter.compare_from_dataframes(df, df.copy())
        
        assert len(result['changes']['added']) == 0
        assert len(result['changes']['removed']) == 0
        assert len(result['changes']['modified']) == 0
    
    def test_invalid_primary_key(self, reporter):
        """测试主键不存在的情况"""
        df_old = pd.DataFrame({
            'id': [1, 2],
            'name': ['Alice', 'Bob']
        })
        
        df_new = pd.DataFrame({
            'user_id': [1, 2],  # 列名不同
            'name': ['Alice', 'Bob']
        })
        
        with pytest.raises(ValueError, match="主键列.*不存在"):
            reporter.find_changes(df_old, df_new)
