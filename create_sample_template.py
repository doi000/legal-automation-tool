"""
サンプル契約書テンプレートを生成するスクリプト。
python create_sample_template.py で実行。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from services.word_generator import WordGenerator

output = os.path.join(os.path.dirname(__file__), "templates", "contract_template.docx")
WordGenerator.create_sample_template(output)
print(f"サンプルテンプレートを生成しました: {output}")
