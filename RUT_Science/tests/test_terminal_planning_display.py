"""Reproduce the terminal's structured-question failure through its real loop."""
import asyncio
from contextlib import nullcontext
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from rich.console import Console
from rut_science.science_bot import terminal
from rut_science.science_bot.general.conversation import GeneralSession

ROOT=Path(__file__).resolve().parents[2]


class TerminalPlanningDisplayTests(unittest.TestCase):
    def test_complete_answer_takes_precedence_over_structured_questions(self):
        value={'answer':'研究任务：目标和边界\n为什么问：明确实验单位',
               'questions':[{'field':'experimental_unit','question':'独立单位是什么？'}]}
        self.assertEqual(terminal.response_text(value),value['answer'])

    def test_empty_question_array_does_not_hide_answer(self):
        self.assertEqual(terminal.response_text({'answer':'当前计划可供复核','questions':[]}),'当前计划可供复核')

    def test_structured_fallback_keeps_question_reason_and_options(self):
        out=terminal.response_text({'questions':[{'question':'本轮研究目的？','rationale':'决定证据要求',
            'options':[{'value':'comparison','label':'比较'},'预测']} ]})
        self.assertIn('本轮研究目的？',out);self.assertIn('为什么问：决定证据要求',out)
        self.assertIn('1. 比较',out);self.assertIn('2. 预测',out)

    def test_legacy_questions_and_structured_evidence_are_displayed_safely(self):
        stream=io.StringIO();console=Console(file=stream,width=150,force_terminal=False)
        terminal.show_response(console,{'questions':['选择数据集','声明预算'],
            'evidence_refs':[{'ref':'source1'},'source2']})
        out=stream.getvalue()
        self.assertIn('选择数据集',out);self.assertIn('声明预算',out);self.assertIn('source1',out);self.assertIn('source2',out)

    def test_terminal_controls_remain_escaped(self):
        out=terminal.response_text({'questions':[{'question':'Q\x1b[31m','rationale':'原因'}]})
        self.assertNotIn('\x1b',out);self.assertIn('\\u001b',out)

    def test_real_interactive_natural_and_command_routes_do_not_join_dicts(self):
        (ROOT/'.local').mkdir(exist_ok=True)
        for message in ['我想复现LinearNO论文，但是不知道应该验证哪个结论，先不要训练','/plan']:
            with self.subTest(message=message),tempfile.TemporaryDirectory(dir=ROOT/'.local') as folder:
                session=GeneralSession.create(Path(folder),backend='offline')
                inputs=iter([message,'/exit'])
                async def prompt(*args,**kwargs):return next(inputs)
                stream=io.StringIO();console=Console(file=stream,width=160,force_terminal=False,highlight=False)
                with patch.object(terminal,'open_session',return_value=session), \
                     patch.object(terminal,'Console',return_value=console), \
                     patch.object(terminal,'PromptSession',return_value=SimpleNamespace(prompt_async=prompt)), \
                     patch.object(terminal,'patch_stdout',return_value=nullcontext()):
                    self.assertEqual(asyncio.run(terminal.interactive(SimpleNamespace())),0)
                out=stream.getvalue()
                self.assertNotIn('TypeError',out)
                self.assertIn('研究',out)
                self.assertIsNotNone(session.meta.get('planning_ref'))
                if not message.startswith('/'):
                    self.assertIn('选择编号',out)
                    self.assertNotIn('为什么问：',out)


if __name__=='__main__':unittest.main()
