"""提交前证券身份校验：真实 Git 中文路径、结构化公司名和错误阻断。"""
from contextlib import redirect_stdout
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import verify_tickers as verify


TRUTH = {
    "688017.SHG": {"name_zh": "绿的谐波", "name_en": "Leader Harmonious Drive Systems"},
    "603297.SHG": {"name_zh": "永新光学", "name_en": "Ningbo Yongxin Optics"},
    "600570.SHG": {"name_zh": "Hundsun Technologies", "name_en": "Hundsun Technologies Inc"},
    "OKTA.US": {"name_zh": "Okta", "name_en": "Okta Inc"},
    "DDOG.US": {"name_zh": "Datadog", "name_en": "Datadog Inc"},
}


class TickerValidationTests(unittest.TestCase):
    def setUp(self):
        mocked = patch.object(verify, "lookup_by_ticker", side_effect=TRUTH.get)
        mocked.start()
        self.addCleanup(mocked.stop)

    def scan(self, html):
        return verify.scan_file("报告.html", text=html)

    def test_graph_nodes_use_company_labels_and_ignore_edges_and_descriptors(self):
        html = '''<div class="cnode" data-id="OKTA.US" data-desc="Okta / 身份授权"
          data-status="水位90"><b>OKTA</b><small>身份授权</small></div>
          <span data-from="OKTA.US" data-to="DDOG.US"></span><p>图中的关键是身份授权。</p>
          <p>DDOG.US（已完成同源行情和代码交叉验证）；但它是观测平台。</p>'''
        self.assertEqual(self.scan(html), ([], []))
        pairs, _ = verify._html_pairs(html)
        self.assertEqual(pairs, [("OKTA.US", "Okta")])

    def test_row_joins_own_ticker_and_name_without_crossing_into_neighbor(self):
        correct = '''<div class="row"><div class="tk">688017<a href="/chart/688017.SHG">图</a></div>
          <div class="nmcell"><div class="t">绿的谐波·谐波减速器</div><div class="d">水位与判断</div></div></div>'''
        self.assertEqual(self.scan(correct), ([], []))
        wrong = correct.replace("绿的谐波·", "永新光学·")
        mismatches, warnings = self.scan(correct + wrong)
        self.assertEqual(warnings, [])
        self.assertEqual([(m["ticker"], m["claimed_zh"]) for m in mismatches],
                         [("688017.SHG", "永新光学")])

    def test_explicit_bold_company_and_ticker_can_block_wrong_name(self):
        self.assertEqual(self.scan("<b>绿的谐波（688017.SHG）</b>但它是减速器"), ([], []))
        mismatches, _ = self.scan("<b>永新光学（688017.SHG）</b>")
        self.assertEqual(len(mismatches), 1)
        self.assertEqual(mismatches[0]["claimed_zh"], "永新光学")

    def test_candidate_company_title_uses_unambiguous_ticker_mapping(self):
        html = '''<p>OKTA.US</p><article class="candidate" data-ticker="OKTA">
          <h3>OKTA <span>Datadog</span></h3><p>身份授权与水位</p></article>'''
        mismatches, _ = self.scan(html)
        self.assertEqual([(m["ticker"], m["claimed_zh"]) for m in mismatches], [("OKTA.US", "Datadog")])

    def test_different_companies_cannot_match_generic_name_suffix(self):
        self.assertFalse(verify._name_matches("中天科技", "金发科技", "Kingfa Technology"))
        self.assertFalse(verify._name_matches("Other Technologies", "Hundsun", "Hundsun Technologies Inc"))
        self.assertFalse(verify._name_matches("永新光学 Leader", "绿的谐波", "Leader Harmonious"))
        self.assertTrue(verify._name_matches("日月光ASE", "日月光 ASE 封测", "ASE Technology"))
        self.assertTrue(verify._name_matches("村田Murata", "村田 MLCC", "Murata Manufacturing"))

    def test_existing_mixed_language_and_annotated_aliases_use_company_identity(self):
        self.assertTrue(verify._name_matches("Eshallgo(原误标亿航)", "Eshallgo 办公设备(非亿航)", "Eshallgo Inc"))
        self.assertTrue(verify._name_matches("F5", "F5", "F5 Networks Inc"))
        self.assertTrue(verify._name_matches("Karman太空与防务", "卡曼太空与防务", "Karman Holdings"))
        self.assertTrue(verify._name_matches("日本化学工业 NipponChem", "日本化学产业", "Nippon Chemical Industrial Co Ltd"))
        self.assertFalse(verify._name_matches("Different Cloud", "Example Cloud", "Example Cloud Technology"))

    def test_english_only_truth_chinese_claim_requires_review_not_fabricated_match(self):
        mismatches, warnings = self.scan("<b>恒生电子（600570.SHG）</b>")
        self.assertEqual(mismatches, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("中文别名需核对", warnings[0])
        mismatches, warnings = self.scan("<b>Hundsun（600570.SHG）</b>")
        self.assertEqual((mismatches, warnings), ([], []))

    def test_unknown_ticker_is_warning_even_without_company_declaration(self):
        mismatches, warnings = self.scan("<p>未来研究 NEW.US（待核对）</p>")
        self.assertEqual(mismatches, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("NOT IN TICKER_TRUTH", warnings[0])

    def test_csv_explicit_wrong_chinese_company_remains_blocked(self):
        text = "date,theme,eodhd_symbol,name\n2026-09-28,测试,688017.SHG,永新光学\n"
        mismatches, warnings = verify.scan_file("forward_picks.csv", text=text)
        self.assertEqual(warnings, [])
        self.assertEqual(len(mismatches), 1)

    def test_existing_magic_and_generator_skip_contract_is_preserved(self):
        wrong = "<b>永新光学（688017.SHG）</b>"
        self.assertEqual(verify.scan_file("report.html", text="<!--ticker-verify: skip-->" + wrong), ([], []))
        self.assertEqual(verify.scan_file("_gen_example.py", text=wrong), ([], []))

    def test_real_git_unicode_paths_and_staged_blob_cannot_be_hidden_by_worktree_edit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def git(*args):
                return subprocess.run(["git", *args], cwd=root, capture_output=True, check=True)
            git("init", "--quiet")
            git("config", "core.quotePath", "true")
            relative = "中文目录/研究报告.html"
            target = root / relative
            target.parent.mkdir()
            wrong = "<b>永新光学（688017.SHG）</b>"
            target.write_text(wrong, encoding="utf-8")
            git("add", "--", relative)
            target.write_text("<b>绿的谐波（688017.SHG）</b>", encoding="utf-8")
            self.assertEqual(verify.get_staged_files(root), [relative])
            self.assertEqual(verify.read_staged_file(relative, root), wrong)
            with patch.object(verify, "_repo_root", return_value=str(root)), \
                    patch.object(sys, "argv", ["verify_tickers.py", "--staged"]), \
                    redirect_stdout(io.StringIO()) as output:
                self.assertEqual(verify.main(), 1)
            self.assertIn("永新光学", output.getvalue())
            self.assertIn("scanned 1 files", output.getvalue())

    def test_git_enumeration_failure_is_not_reported_as_empty_success(self):
        with patch.object(verify, "get_staged_files", side_effect=subprocess.CalledProcessError(128, "git")), \
                patch.object(sys, "argv", ["verify_tickers.py", "--staged"]), \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(verify.main(), 2)
        self.assertIn("[ERROR]", output.getvalue())

    def test_json_uses_explicit_name_fields_not_neighboring_descriptions(self):
        good = '[{"ticker":"OKTA.US","name_zh":"Okta","description":"身份控制面"}]'
        self.assertEqual(verify.scan_file('demo.json', good), ([], []))
        wrong = '{"candidates":[{"tk":"688017.SHG","t":"永新光学 · 演示"}]}'
        self.assertEqual(len(verify.scan_file('demo.json', wrong)[0]), 1)

    def test_markdown_code_examples_do_not_claim_company_names(self):
        self.assertEqual(verify.scan_file('guide.md', '调用 `OKTA.US` 即可取得数据。'), ([], []))
        self.assertEqual(len(verify.scan_file('guide.md', '永新光学（688017.SHG）')[0]), 1)


if __name__ == "__main__":
    unittest.main()
