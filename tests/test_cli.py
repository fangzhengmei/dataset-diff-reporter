import pytest
import pandas as pd
import sqlite3
import os
import tempfile
import sys
from io import StringIO
from dataset_diff_reporter.cli import main


@pytest.fixture
def test_db():
    """创建测试用的SQLite数据库"""
    # 创建临时数据库文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
        db_path = f.name
    
    # 连接数据库并创建测试数据
    conn = sqlite3.connect(db_path)
    
    # 旧表数据
    df_old = pd.DataFrame({
        'id': [1, 2, 3, 4],
        'name': ['Alice', 'Bob', 'Charlie', 'David'],
        'age': [25, 30, 35, 40],
        'salary': [50000, 60000, 70000, 80000]
    })
    
    # 新表数据（包含增删改）
    df_new = pd.DataFrame({
        'id': [1, 2, 3, 5],  # 删除了id=4，新增了id=5
        'name': ['Alice', 'Bob', 'Charles', 'Eve'],  # Charlie改名为Charles
        'age': [25, 31, 35, 28],  # Bob的年龄从30改为31
        'salary': [52000, 60000, 75000, 45000]  # Alice和Charlie的工资变了
    })
    
    df_old.to_sql('table_old', conn, index=False, if_exists='replace')
    df_new.to_sql('table_new', conn, index=False, if_exists='replace')
    
    conn.close()
    
    yield db_path
    
    # 清理临时文件
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def composite_key_db():
    """创建使用复合主键的测试数据库"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
        db_path = f.name
    
    conn = sqlite3.connect(db_path)
    
    # 旧表数据（使用复合主键：department + employee_id）
    df_old = pd.DataFrame({
        'department': ['IT', 'IT', 'HR', 'HR'],
        'employee_id': [1, 2, 1, 2],
        'name': ['Alice', 'Bob', 'Charlie', 'David'],
        'salary': [50000, 60000, 55000, 65000]
    })
    
    # 新表数据
    df_new = pd.DataFrame({
        'department': ['IT', 'IT', 'HR', 'Finance'],
        'employee_id': [1, 3, 1, 1],
        'name': ['Alice', 'Eve', 'Charlie', 'Frank'],
        'salary': [52000, 70000, 55000, 80000]
    })
    
    df_old.to_sql('table_old', conn, index=False, if_exists='replace')
    df_new.to_sql('table_new', conn, index=False, if_exists='replace')
    
    conn.close()
    
    yield db_path
    
    if os.path.exists(db_path):
        os.unlink(db_path)


class TestCLI:
    """测试命令行入口"""
    
    def test_cli_basic(self, test_db, capsys):
        """测试基本的命令行使用"""
        args = [
            '--db', test_db,
            '--old-table', 'table_old',
            '--new-table', 'table_new',
            '--pk', 'id'
        ]
        
        exit_code = main(args)
        
        # 检查退出码
        assert exit_code == 0
        
        # 检查输出
        captured = capsys.readouterr()
        output = captured.out
        
        # 检查报告包含关键信息
        assert "数据集快照对比报告" in output
        assert "新增记录" in output
        assert "删除记录" in output
        assert "修改记录" in output
        assert "数值变化统计" in output
    
    def test_cli_output_to_file(self, test_db):
        """测试输出到文件"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            output_path = f.name
        
        try:
            args = [
                '--db', test_db,
                '--old-table', 'table_old',
                '--new-table', 'table_new',
                '--pk', 'id',
                '--output', output_path
            ]
            
            exit_code = main(args)
            
            # 检查退出码
            assert exit_code == 0
            
            # 检查文件是否创建
            assert os.path.exists(output_path)
            
            # 检查文件内容
            with open(output_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            assert "数据集快照对比报告" in content
            assert "新增记录" in content
            assert "删除记录" in content
            
        finally:
            # 清理临时文件
            if os.path.exists(output_path):
                os.unlink(output_path)
    
    def test_cli_custom_title(self, test_db, capsys):
        """测试自定义报告标题"""
        custom_title = "月度销售数据对比报告"
        
        args = [
            '--db', test_db,
            '--old-table', 'table_old',
            '--new-table', 'table_new',
            '--pk', 'id',
            '--title', custom_title
        ]
        
        exit_code = main(args)
        
        assert exit_code == 0
        
        captured = capsys.readouterr()
        output = captured.out
        
        assert custom_title in output
    
    def test_cli_composite_primary_key(self, composite_key_db, capsys):
        """测试使用复合主键"""
        args = [
            '--db', composite_key_db,
            '--old-table', 'table_old',
            '--new-table', 'table_new',
            '--pk', 'department', 'employee_id'
        ]
        
        exit_code = main(args)
        
        assert exit_code == 0
        
        captured = capsys.readouterr()
        output = captured.out
        
        assert "数据集快照对比报告" in output
        # 检查复合主键的对比结果
        # 新增: (IT,3), (Finance,1)
        # 删除: (IT,2), (HR,2)
        # 修改: (IT,1) - salary 50000→52000
        assert "2 条" in output  # 新增记录数
        assert "1 条" in output  # 修改记录数
    
    def test_cli_ignore_columns(self, test_db, capsys):
        """测试忽略指定列"""
        args = [
            '--db', test_db,
            '--old-table', 'table_old',
            '--new-table', 'table_new',
            '--pk', 'id',
            '--ignore-columns', 'salary'
        ]
        
        exit_code = main(args)
        
        assert exit_code == 0
        
        captured = capsys.readouterr()
        output = captured.out
        
        # 由于忽略了salary列，id=1的修改（只有salary变化）应该被忽略
        # 但报告中仍然会显示salary的数值统计
        assert "数据集快照对比报告" in output
    
    def test_cli_missing_required_args(self):
        """测试缺少必需参数"""
        # 缺少--db参数
        args = [
            '--old-table', 'table_old',
            '--new-table', 'table_new',
            '--pk', 'id'
        ]
        
        with pytest.raises(SystemExit) as exc_info:
            main(args)
        
        # argparse 在缺少必需参数时会退出，退出码为 2
        assert exc_info.value.code != 0
    
    def test_cli_invalid_db_path(self):
        """测试无效的数据库路径"""
        args = [
            '--db', '/path/to/nonexistent.db',
            '--old-table', 'table_old',
            '--new-table', 'table_new',
            '--pk', 'id'
        ]
        
        exit_code = main(args)
        
        # 应该返回非零退出码
        assert exit_code != 0
    
    def test_cli_invalid_table_name(self, test_db):
        """测试无效的表名"""
        args = [
            '--db', test_db,
            '--old-table', 'nonexistent_table',
            '--new-table', 'table_new',
            '--pk', 'id'
        ]
        
        exit_code = main(args)
        
        # 应该返回非零退出码
        assert exit_code != 0
    
    def test_cli_help_output(self, capsys):
        """测试帮助输出"""
        with pytest.raises(SystemExit) as exc_info:
            main(['--help'])
        
        assert exc_info.value.code == 0
        
        captured = capsys.readouterr()
        output = captured.out
        
        # 检查帮助信息包含关键内容
        assert "数据集快照对比工具" in output
        assert "--db" in output
        assert "--old-table" in output
        assert "--new-table" in output
        assert "--pk" in output
        assert "--output" in output
        assert "--title" in output
