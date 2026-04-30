import argparse
import sys
from typing import List
from .core import (
    DatasetDiffReporter,
    DatasetDiffError,
    InvalidInputError,
    SecurityError,
    DataIntegrityError,
    DatabaseError
)


def main(argv: List[str] = None) -> int:
    """
    命令行入口函数
    
    Args:
        argv: 命令行参数列表，如果为None则使用sys.argv[1:]
        
    Returns:
        退出码，0表示成功，非0表示失败
        
    Exit Codes:
        0: 成功
        1: 通用错误
        2: 无效输入参数
        3: 安全风险（如SQL注入、路径遍历）
        4: 数据完整性问题（如重复主键）
        5: 数据库操作错误
    """
    parser = argparse.ArgumentParser(
        description='数据集快照对比工具 - 对比SQLite数据库中的两张表并生成Markdown报告',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  # 对比两张表并输出到控制台
  python -m dataset_diff_reporter --db my.db --old-table table_v1 --new-table table_v2 --pk id

  # 对比两张表并保存报告到文件
  python -m dataset_diff_reporter --db my.db --old-table table_v1 --new-table table_v2 --pk id --output report.md

  # 使用复合主键
  python -m dataset_diff_reporter --db my.db --old-table table_v1 --new-table table_v2 --pk dept_id emp_id

  # 自定义报告标题
  python -m dataset_diff_reporter --db my.db --old-table table_v1 --new-table table_v2 --pk id --title "月度数据对比报告"
        '''
    )
    
    # 必需参数
    parser.add_argument(
        '--db', '--database',
        required=True,
        dest='db_path',
        help='SQLite数据库文件路径'
    )
    
    parser.add_argument(
        '--old-table',
        required=True,
        dest='table_old',
        help='旧数据表名'
    )
    
    parser.add_argument(
        '--new-table',
        required=True,
        dest='table_new',
        help='新数据表名'
    )
    
    parser.add_argument(
        '--pk', '--primary-key',
        required=True,
        nargs='+',
        dest='primary_keys',
        help='主键列名（支持复合主键，多个列名用空格分隔）'
    )
    
    # 可选参数
    parser.add_argument(
        '-o', '--output',
        dest='output_file',
        help='输出文件路径（如果不指定，则输出到控制台）'
    )
    
    parser.add_argument(
        '--title',
        default='数据集快照对比报告',
        dest='report_title',
        help='报告标题（默认：数据集快照对比报告）'
    )
    
    parser.add_argument(
        '--ignore-columns',
        nargs='*',
        default=[],
        dest='ignore_columns',
        help='忽略比较的列名列表'
    )
    
    # 解析参数
    args = parser.parse_args(argv)
    
    try:
        # 创建对比器
        reporter = DatasetDiffReporter(primary_keys=args.primary_keys)
        
        # 进行对比
        result = reporter.compare_from_sqlite(
            db_path=args.db_path,
            table_name_old=args.table_old,
            table_name_new=args.table_new,
            ignore_columns=args.ignore_columns
        )
        
        # 生成报告
        report = reporter.generate_markdown_report(
            schema_info=result['schema_info'],
            changes=result['changes'],
            numeric_stats=result['numeric_stats'],
            report_title=args.report_title
        )
        
        # 输出报告
        if args.output_file:
            with open(args.output_file, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f'报告已保存到: {args.output_file}')
        else:
            print(report)
        
        return 0
        
    except InvalidInputError as e:
        print(f"\n【输入错误】", file=sys.stderr)
        print(f"{e}", file=sys.stderr)
        print(f"\n提示: 请检查输入参数是否正确。使用 --help 查看帮助信息。", file=sys.stderr)
        return 2
        
    except SecurityError as e:
        print(f"\n【安全警告】", file=sys.stderr)
        print(f"{e}", file=sys.stderr)
        print(f"\n提示: 检测到潜在的安全风险，操作已中止。", file=sys.stderr)
        return 3
        
    except DataIntegrityError as e:
        print(f"\n【数据完整性错误】", file=sys.stderr)
        print(f"{e}", file=sys.stderr)
        print(f"\n提示: 请检查数据中是否存在重复主键或其他完整性问题。", file=sys.stderr)
        return 4
        
    except DatabaseError as e:
        print(f"\n【数据库错误】", file=sys.stderr)
        print(f"{e}", file=sys.stderr)
        print(f"\n提示: 请检查数据库连接和表结构。", file=sys.stderr)
        return 5
        
    except DatasetDiffError as e:
        print(f"\n【对比错误】", file=sys.stderr)
        print(f"{e}", file=sys.stderr)
        return 1
        
    except Exception as e:
        print(f"\n【意外错误】", file=sys.stderr)
        print(f"类型: {type(e).__name__}", file=sys.stderr)
        print(f"详情: {e}", file=sys.stderr)
        print(f"\n提示: 如果问题持续存在，请检查数据格式或提交Issue。", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
