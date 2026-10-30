"""Build interface examples without models, real data or experiment execution."""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'RUT_Science'))
sys.dont_write_bytecode=True
from rut_science.science_bot.presentation import terminal_preview_html,browser_preview_html,delivery_html
from rut_science.science_bot.interface_demo import example_state
from rut_science.science_bot.general.planning.runtime import _plan


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'examples/interfaces')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    artifacts={'terminal.html':terminal_preview_html(),'browser.html':browser_preview_html(),
               'delivery.html':delivery_html(_plan(example_state()))}
    for name,content in artifacts.items():
        (args.output/name).write_text(content,encoding='utf-8',newline='\n')
    print('Created terminal.html, browser.html and delivery.html; synthetic content, no model requests.')


if __name__=='__main__':main()
