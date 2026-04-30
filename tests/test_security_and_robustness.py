"""
测试输入安全验证和边界鲁棒性
包括：输入验证、安全防护、数据完整性、原始数据保护
"""
import pytest
import pandas as pd
import sqlite3
import os
import tempfile
from dataset_diff_reporter import (
    DatasetDiffReporter,
    DatasetDiffError,
    InvalidInputError,
    SecurityError,
    DataIntegrityError,
    DatabaseError
)


class TestPrimaryKeyValidation:
    """测试主键验证"""
    
    def test_primary_keys_none(self):
        """测试主键为 None"""
        with pytest.raises(InvalidInputError) as exc_info:
            DatasetDiffReporter(primary_keys=None)
        
        assert "主键列表不能为 None" in str(exc_info.value)
    
    def test_primary_keys_empty_list(self):
        """测试主键为空列表"""
        with pytest.raises(InvalidInputError) as exc_info:
            DatasetDiffReporter(primary_keys=[])
        
        assert "不能为空" in str(exc_info.value)
        assert "至少指定一个主键列" in str(exc_info.value)
    
    def test_primary_keys_not_list(self):
        """测试主键不是列表类型"""
        with pytest.raises(InvalidInputError) as exc_info:
            DatasetDiffReporter(primary_keys="id")
        
        assert "必须是列表或元组类型" in str(exc_info.value)
        assert "str" in str(exc_info.value)
    
    def test_primary_keys_with_invalid_type_elements(self):
        """测试主键列表包含非字符串元素"""
        with pytest.raises(InvalidInputError) as exc_info:
            DatasetDiffReporter(primary_keys=[1, 2])
        
        assert "主键列名必须是字符串类型" in str(exc_info.value)
        assert "第 1 个主键" in str(exc_info.value)
        assert "int" in str(exc_info.value)
    
    def test_primary_keys_with_empty_string(self):
        """测试主键列表包含空字符串"""
        with pytest.raises(InvalidInputError) as exc_info:
            DatasetDiffReporter(primary_keys=["id", ""])
        
        assert "不能为空或仅包含空白字符" in str(exc_info.value)
        assert "第 2 个" in str(exc_info.value)
    
    def test_primary_keys_with_whitespace_only(self):
        """测试主键列表包含仅空白字符的字符串"""
        with pytest.raises(InvalidInputError) as exc_info:
            DatasetDiffReporter(primary_keys=["id", "   \t\n  "])
        
        assert "不能为空或仅包含空白字符" in str(exc_info.value)
    
    def test_primary_keys_with_invalid_identifier(self):
        """测试主键列名格式不合法"""
        # 以数字开头
        with pytest.raises(InvalidInputError) as exc_info:
            DatasetDiffReporter(primary_keys=["1id"])
        
        assert "格式不合法" in str(exc_info.value)
        assert "必须以字母或下划线开头" in str(exc_info.value)
        
        # 包含特殊字符
        with pytest.raises(InvalidInputError):
            DatasetDiffReporter(primary_keys=["id-name"])
        
        with pytest.raises(InvalidInputError):
            DatasetDiffReporter(primary_keys=["id@name"])
    
    def test_primary_keys_valid(self):
        """测试合法的主键列表"""
        # 单主键
        reporter = DatasetDiffReporter(primary_keys=["id"])
        assert reporter.primary_keys == ["id"]
        
        # 复合主键
        reporter = DatasetDiffReporter(primary_keys=["dept_id", "emp_id"])
        assert reporter.primary_keys == ["dept_id", "emp_id"]
        
        # 以下划线开头
        reporter = DatasetDiffReporter(primary_keys=["_id"])
        assert reporter.primary_keys == ["_id"]


class TestDataFrameValidation:
    """测试 DataFrame 输入验证"""
    
    def test_dataframe_none(self):
        """测试 DataFrame 为 None"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        with pytest.raises(InvalidInputError) as exc_info:
            reporter.align_schema(df_old=None, df_new=pd.DataFrame())
        
        assert "不能为 None" in str(exc_info.value)
        assert "旧数据集" in str(exc_info.value)
        
        with pytest.raises(InvalidInputError):
            reporter.align_schema(df_old=pd.DataFrame(), df_new=None)
    
    def test_dataframe_not_dataframe(self):
        """测试输入不是 DataFrame 类型"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        with pytest.raises(InvalidInputError) as exc_info:
            reporter.align_schema(df_old=[1, 2, 3], df_new=pd.DataFrame())
        
        assert "必须是 pandas DataFrame 类型" in str(exc_info.value)
        assert "list" in str(exc_info.value)
    
    def test_primary_key_not_in_dataframe(self):
        """测试主键列不存在于 DataFrame 中"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        df_old = pd.DataFrame({
            'not_id': [1, 2],
            'name': ['Alice', 'Bob']
        })
        
        df_new = pd.DataFrame({
            'id': [1, 2],
            'name': ['Alice', 'Bob']
        })
        
        with pytest.raises(InvalidInputError) as exc_info:
            reporter.find_changes(df_old, df_new)
        
        assert "主键列 'id' 不存在于旧数据集中" in str(exc_info.value)
        assert "列" in str(exc_info.value)
        assert "'not_id'" in str(exc_info.value)
        assert "'name'" in str(exc_info.value)


class TestSQLInjectionProtection:
    """测试 SQL 注入防护"""
    
    @pytest.fixture
    def test_db(self):
        """创建测试数据库"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
            db_path = f.name
        
        conn = sqlite3.connect(db_path)
        df = pd.DataFrame({
            'id': [1, 2, 3],
            'name': ['Alice', 'Bob', 'Charlie'],
            'value': [100, 200, 300]
        })
        df.to_sql('valid_table', conn, index=False, if_exists='replace')
        conn.close()
        
        yield db_path
        
        if os.path.exists(db_path):
            try:
                os.unlink(db_path)
            except:
                pass
    
    def test_table_name_with_semicolon(self, test_db):
        """测试表名包含分号（SQL注入尝试）"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        with pytest.raises(SecurityError) as exc_info:
            reporter.compare_from_sqlite(
                db_path=test_db,
                table_name_old="valid_table; DROP TABLE valid_table;",
                table_name_new="valid_table"
            )
        
        assert "SQL注入风险" in str(exc_info.value)
        assert "包含危险字符" in str(exc_info.value)
    
    def test_table_name_with_sql_comment(self, test_db):
        """测试表名包含 SQL 注释"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        with pytest.raises(SecurityError):
            reporter.compare_from_sqlite(
                db_path=test_db,
                table_name_old="valid_table --",
                table_name_new="valid_table"
            )
        
        with pytest.raises(SecurityError):
            reporter.compare_from_sqlite(
                db_path=test_db,
                table_name_old="/* comment */valid_table",
                table_name_new="valid_table"
            )
    
    def test_table_name_with_quotes(self, test_db):
        """测试表名包含引号"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        with pytest.raises(SecurityError):
            reporter.compare_from_sqlite(
                db_path=test_db,
                table_name_old="valid_table' OR '1'='1",
                table_name_new="valid_table"
            )
        
        with pytest.raises(SecurityError):
            reporter.compare_from_sqlite(
                db_path=test_db,
                table_name_old='valid_table" OR "1"="1',
                table_name_new="valid_table"
            )
    
    def test_table_name_with_backslash(self, test_db):
        """测试表名包含反斜杠"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        with pytest.raises(SecurityError):
            reporter.compare_from_sqlite(
                db_path=test_db,
                table_name_old="valid_table\\",
                table_name_new="valid_table"
            )
    
    def test_table_name_empty(self, test_db):
        """测试表名为空"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        with pytest.raises(InvalidInputError):
            reporter.compare_from_sqlite(
                db_path=test_db,
                table_name_old="",
                table_name_new="valid_table"
            )
        
        with pytest.raises(InvalidInputError):
            reporter.compare_from_sqlite(
                db_path=test_db,
                table_name_old="   ",
                table_name_new="valid_table"
            )
    
    def test_table_name_none(self, test_db):
        """测试表名为 None"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        with pytest.raises(InvalidInputError) as exc_info:
            reporter.compare_from_sqlite(
                db_path=test_db,
                table_name_old=None,
                table_name_new="valid_table"
            )
        
        assert "不能为 None" in str(exc_info.value)
    
    def test_table_name_invalid_identifier(self, test_db):
        """测试表名格式不合法"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        # 以数字开头
        with pytest.raises(InvalidInputError):
            reporter.compare_from_sqlite(
                db_path=test_db,
                table_name_old="123table",
                table_name_new="valid_table"
            )
        
        # 包含特殊字符
        with pytest.raises(InvalidInputError):
            reporter.compare_from_sqlite(
                db_path=test_db,
                table_name_old="table-name",
                table_name_new="valid_table"
            )
    
    def test_table_not_exist(self, test_db):
        """测试表不存在"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        with pytest.raises(InvalidInputError) as exc_info:
            reporter.compare_from_sqlite(
                db_path=test_db,
                table_name_old="nonexistent_table",
                table_name_new="valid_table"
            )
        
        assert "不存在于数据库中" in str(exc_info.value)
        assert "数据库中的表" in str(exc_info.value)
        assert "valid_table" in str(exc_info.value)


class TestPathTraversalProtection:
    """测试路径遍历防护"""
    
    def test_db_path_with_dot_dot(self):
        """测试数据库路径包含 ..（路径遍历尝试）"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        with pytest.raises(SecurityError) as exc_info:
            reporter.compare_from_sqlite(
                db_path="../../secret.db",
                table_name_old="table1",
                table_name_new="table2"
            )
        
        assert "路径遍历攻击风险" in str(exc_info.value)
        assert "包含 '..'" in str(exc_info.value)
    
    def test_db_path_with_unc_path(self):
        """测试 UNC 路径（仅 Windows）"""
        if os.name != 'nt':
            pytest.skip("UNC 路径测试仅在 Windows 上运行")
        
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        with pytest.raises(SecurityError):
            reporter.compare_from_sqlite(
                db_path="\\\\server\\share\\db.db",
                table_name_old="table1",
                table_name_new="table2"
            )
        
        with pytest.raises(SecurityError):
            reporter.compare_from_sqlite(
                db_path="//server/share/db.db",
                table_name_old="table1",
                table_name_new="table2"
            )
    
    def test_db_path_empty(self):
        """测试数据库路径为空"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        with pytest.raises(InvalidInputError):
            reporter.compare_from_sqlite(
                db_path="",
                table_name_old="table1",
                table_name_new="table2"
            )
    
    def test_db_path_none(self):
        """测试数据库路径为 None"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        with pytest.raises(InvalidInputError):
            reporter.compare_from_sqlite(
                db_path=None,
                table_name_old="table1",
                table_name_new="table2"
            )
    
    def test_db_file_not_exist(self):
        """测试数据库文件不存在"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        with pytest.raises(InvalidInputError) as exc_info:
            reporter.compare_from_sqlite(
                db_path="/nonexistent/path/db.db",
                table_name_old="table1",
                table_name_new="table2"
            )
        
        assert "数据库文件不存在" in str(exc_info.value)
        assert "当前工作目录" in str(exc_info.value)


class TestDataIntegrity:
    """测试数据完整性验证"""
    
    def test_duplicate_primary_keys(self):
        """测试重复主键"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        # 旧数据有重复主键
        df_old = pd.DataFrame({
            'id': [1, 2, 2, 3],  # id=2 重复
            'name': ['Alice', 'Bob', 'Bob2', 'Charlie'],
            'value': [100, 200, 250, 300]
        })
        
        df_new = pd.DataFrame({
            'id': [1, 2, 3],
            'name': ['Alice', 'Bob', 'Charlie'],
            'value': [100, 200, 300]
        })
        
        with pytest.raises(DataIntegrityError) as exc_info:
            reporter.find_changes(df_old, df_new)
        
        assert "存在重复主键" in str(exc_info.value)
        assert "旧数据集" in str(exc_info.value)
        assert "(2,)" in str(exc_info.value)  # 重复的主键值
    
    def test_duplicate_composite_primary_keys(self):
        """测试复合主键重复"""
        reporter = DatasetDiffReporter(primary_keys=["dept_id", "emp_id"])
        
        df_old = pd.DataFrame({
            'dept_id': [1, 1, 2, 2, 2],  # (2, 1) 重复
            'emp_id': [1, 2, 1, 1, 2],
            'name': ['Alice', 'Bob', 'Charlie', 'Charlie2', 'David'],
            'salary': [50000, 60000, 55000, 56000, 65000]
        })
        
        df_new = pd.DataFrame({
            'dept_id': [1, 1, 2, 2],
            'emp_id': [1, 2, 1, 2],
            'name': ['Alice', 'Bob', 'Charlie', 'David'],
            'salary': [50000, 60000, 55000, 65000]
        })
        
        with pytest.raises(DataIntegrityError) as exc_info:
            reporter.find_changes(df_old, df_new)
        
        assert "存在重复主键" in str(exc_info.value)
        assert "(2, 1)" in str(exc_info.value)


class TestOriginalDataProtection:
    """测试原始数据保护（无副作用）"""
    
    def test_find_changes_does_not_modify_original(self):
        """测试 find_changes 不修改原始 DataFrame"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        df_old = pd.DataFrame({
            'id': [1, 2, 3],
            'name': ['Alice', 'Bob', 'Charlie'],
            'value': [100, 200, 300]
        })
        
        df_new = pd.DataFrame({
            'id': [1, 2, 4],
            'name': ['Alice', 'Robert', 'David'],
            'value': [150, 200, 400]
        })
        
        # 保存原始数据的副本
        df_old_copy = df_old.copy()
        df_new_copy = df_new.copy()
        old_columns = list(df_old.columns)
        new_columns = list(df_new.columns)
        
        # 执行对比
        changes = reporter.find_changes(df_old, df_new)
        
        # 验证原始数据未被修改
        pd.testing.assert_frame_equal(df_old, df_old_copy)
        pd.testing.assert_frame_equal(df_new, df_new_copy)
        assert list(df_old.columns) == old_columns
        assert list(df_new.columns) == new_columns
        
        # 验证 _pk_tuple 列不存在于原始数据中
        assert '_pk_tuple' not in df_old.columns
        assert '_pk_tuple' not in df_new.columns
    
    def test_align_schema_does_not_modify_original(self):
        """测试 align_schema 不修改原始 DataFrame"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        df_old = pd.DataFrame({
            'id': [1, 2],
            'name': ['Alice', 'Bob'],
            'old_col': ['a', 'b']
        })
        
        df_new = pd.DataFrame({
            'id': [1, 2],
            'name': ['Alice', 'Bob'],
            'new_col': ['x', 'y']
        })
        
        df_old_copy = df_old.copy()
        df_new_copy = df_new.copy()
        
        df_old_aligned, df_new_aligned, schema_info = reporter.align_schema(df_old, df_new)
        
        # 验证原始数据未被修改
        pd.testing.assert_frame_equal(df_old, df_old_copy)
        pd.testing.assert_frame_equal(df_new, df_new_copy)
        
        # 验证对齐后的数据包含所有列
        assert 'new_col' in df_old_aligned.columns
        assert 'old_col' in df_new_aligned.columns
    
    def test_calculate_numeric_changes_does_not_modify_original(self):
        """测试 calculate_numeric_changes 不修改原始 DataFrame"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        df_old = pd.DataFrame({
            'id': [1, 2, 3],
            'value': [100, 200, 300]
        })
        
        df_new = pd.DataFrame({
            'id': [1, 2, 3],
            'value': [150, 180, 350]
        })
        
        df_old_copy = df_old.copy()
        df_new_copy = df_new.copy()
        
        stats = reporter.calculate_numeric_changes(df_old, df_new)
        
        # 验证原始数据未被修改
        pd.testing.assert_frame_equal(df_old, df_old_copy)
        pd.testing.assert_frame_equal(df_new, df_new_copy)
    
    def test_compare_from_dataframes_does_not_modify_original(self):
        """测试 compare_from_dataframes 不修改原始 DataFrame"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        df_old = pd.DataFrame({
            'id': [1, 2, 3],
            'name': ['Alice', 'Bob', 'Charlie'],
            'value': [100, 200, 300]
        })
        
        df_new = pd.DataFrame({
            'id': [1, 2, 4],
            'name': ['Alice', 'Robert', 'David'],
            'value': [150, 200, 400]
        })
        
        df_old_copy = df_old.copy()
        df_new_copy = df_new.copy()
        
        result = reporter.compare_from_dataframes(df_old, df_new)
        
        # 验证原始数据未被修改
        pd.testing.assert_frame_equal(df_old, df_old_copy)
        pd.testing.assert_frame_equal(df_new, df_new_copy)


class TestStringListValidation:
    """测试字符串列表参数验证"""
    
    def test_ignore_columns_invalid_type(self):
        """测试 ignore_columns 类型无效"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        df_old = pd.DataFrame({
            'id': [1, 2],
            'name': ['Alice', 'Bob'],
            'value': [100, 200]
        })
        
        df_new = df_old.copy()
        
        with pytest.raises(InvalidInputError) as exc_info:
            reporter.find_changes(df_old, df_new, ignore_columns="value")
        
        assert "必须是列表或元组类型" in str(exc_info.value)
        assert "str" in str(exc_info.value)
    
    def test_ignore_columns_with_invalid_elements(self):
        """测试 ignore_columns 包含非字符串元素"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        df_old = pd.DataFrame({
            'id': [1, 2],
            'name': ['Alice', 'Bob'],
            'value': [100, 200]
        })
        
        df_new = df_old.copy()
        
        with pytest.raises(InvalidInputError):
            reporter.find_changes(df_old, df_new, ignore_columns=["name", 123])
    
    def test_numeric_columns_invalid_type(self):
        """测试 numeric_columns 类型无效"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        df_old = pd.DataFrame({
            'id': [1, 2],
            'value': [100, 200]
        })
        
        df_new = df_old.copy()
        
        with pytest.raises(InvalidInputError):
            reporter.calculate_numeric_changes(df_old, df_new, numeric_columns="value")
    
    def test_numeric_columns_not_exist(self):
        """测试指定的数值列不存在"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        df_old = pd.DataFrame({
            'id': [1, 2],
            'value': [100, 200]
        })
        
        df_new = df_old.copy()
        
        with pytest.raises(InvalidInputError) as exc_info:
            reporter.calculate_numeric_changes(df_old, df_new, numeric_columns=["nonexistent_col"])
        
        assert "不存在于旧数据集中" in str(exc_info.value)


class TestGenerateMarkdownReportValidation:
    """测试 generate_markdown_report 输入验证"""
    
    def test_schema_info_none(self):
        """测试 schema_info 为 None"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        with pytest.raises(InvalidInputError):
            reporter.generate_markdown_report(
                schema_info=None,
                changes={'added': pd.DataFrame(), 'removed': pd.DataFrame(), 'modified': pd.DataFrame()},
                numeric_stats={'columns': {}}
            )
    
    def test_schema_info_not_dict(self):
        """测试 schema_info 不是字典"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        with pytest.raises(InvalidInputError):
            reporter.generate_markdown_report(
                schema_info=[],
                changes={'added': pd.DataFrame(), 'removed': pd.DataFrame(), 'modified': pd.DataFrame()},
                numeric_stats={'columns': {}}
            )
    
    def test_changes_none(self):
        """测试 changes 为 None"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        with pytest.raises(InvalidInputError):
            reporter.generate_markdown_report(
                schema_info={'columns_added': [], 'columns_removed': [], 'columns_common': [], 'dtype_changes': []},
                changes=None,
                numeric_stats={'columns': {}}
            )
    
    def test_numeric_stats_none(self):
        """测试 numeric_stats 为 None"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        with pytest.raises(InvalidInputError):
            reporter.generate_markdown_report(
                schema_info={'columns_added': [], 'columns_removed': [], 'columns_common': [], 'dtype_changes': []},
                changes={'added': pd.DataFrame(), 'removed': pd.DataFrame(), 'modified': pd.DataFrame()},
                numeric_stats=None
            )
    
    def test_report_title_none(self):
        """测试 report_title 为 None（应使用默认值）"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        # 不应抛出异常，应使用默认标题
        report = reporter.generate_markdown_report(
            schema_info={'columns_added': [], 'columns_removed': [], 'columns_common': [], 'dtype_changes': []},
            changes={'added': pd.DataFrame(), 'removed': pd.DataFrame(), 'modified': pd.DataFrame()},
            numeric_stats={'columns': {}},
            report_title=None
        )
        
        assert "数据集快照对比报告" in report
    
    def test_report_title_not_string(self):
        """测试 report_title 不是字符串"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        with pytest.raises(InvalidInputError):
            reporter.generate_markdown_report(
                schema_info={'columns_added': [], 'columns_removed': [], 'columns_common': [], 'dtype_changes': []},
                changes={'added': pd.DataFrame(), 'removed': pd.DataFrame(), 'modified': pd.DataFrame()},
                numeric_stats={'columns': {}},
                report_title=123
            )


class TestExceptionHierarchy:
    """测试异常类层次结构"""
    
    def test_all_exceptions_inherit_from_base(self):
        """测试所有异常都继承自 DatasetDiffError"""
        assert issubclass(InvalidInputError, DatasetDiffError)
        assert issubclass(SecurityError, DatasetDiffError)
        assert issubclass(DataIntegrityError, DatasetDiffError)
        assert issubclass(DatabaseError, DatasetDiffError)
    
    def test_can_catch_with_base_exception(self):
        """测试可以用基类捕获所有异常"""
        reporter = DatasetDiffReporter(primary_keys=["id"])
        
        try:
            reporter.align_schema(df_old=None, df_new=pd.DataFrame())
        except DatasetDiffError as e:
            assert isinstance(e, InvalidInputError)
            assert "不能为 None" in str(e)
